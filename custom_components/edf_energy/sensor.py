from datetime import timedelta
import voluptuous as vol
import logging

from homeassistant.util.dt import (utcnow, now)
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_platform, issue_registry as ir, entity_registry as er, device_registry as dr
import homeassistant.helpers.config_validation as cv

from .electricity.current_consumption import EDFEnergyCurrentElectricityConsumption
from .electricity.current_accumulative_consumption import EDFEnergyCurrentAccumulativeElectricityConsumption
from .electricity.current_accumulative_cost import EDFEnergyCurrentAccumulativeElectricityCost
from .electricity.current_demand import EDFEnergyCurrentElectricityDemand
from .electricity.current_rate import EDFEnergyElectricityCurrentRate
from .electricity.next_rate import EDFEnergyElectricityNextRate
from .electricity.previous_accumulative_consumption import EDFEnergyPreviousAccumulativeElectricityConsumption
from .electricity.previous_accumulative_cost import EDFEnergyPreviousAccumulativeElectricityCost
from .electricity.previous_rate import EDFEnergyElectricityPreviousRate
from .electricity.standing_charge import EDFEnergyElectricityCurrentStandingCharge
from .electricity.previous_accumulative_cost_override import EDFEnergyPreviousAccumulativeElectricityCostOverride
from .electricity.rates_previous_consumption_override import EDFEnergyElectricityPreviousConsumptionOverrideRates
from .electricity.current_total_consumption import EDFEnergyCurrentTotalElectricityConsumption
from .electricity.current_total_export import EDFEnergyCurrentTotalElectricityExport
from .gas.current_rate import EDFEnergyGasCurrentRate
from .gas.next_rate import EDFEnergyGasNextRate
from .gas.previous_rate import EDFEnergyGasPreviousRate
from .gas.previous_accumulative_consumption_cubic_meters import EDFEnergyPreviousAccumulativeGasConsumptionCubicMeters
from .gas.previous_accumulative_consumption_kwh import EDFEnergyPreviousAccumulativeGasConsumptionKwh
from .gas.previous_accumulative_cost import EDFEnergyPreviousAccumulativeGasCost
from .gas.current_consumption import EDFEnergyCurrentGasConsumption
from .gas.current_accumulative_consumption_kwh import EDFEnergyCurrentAccumulativeGasConsumptionKwh
from .gas.current_accumulative_consumption_cubic_meters import EDFEnergyCurrentAccumulativeGasConsumptionCubicMeters
from .gas.current_accumulative_cost import EDFEnergyCurrentAccumulativeGasCost
from .gas.standing_charge import EDFEnergyGasCurrentStandingCharge
from .gas.previous_accumulative_cost_override import EDFEnergyPreviousAccumulativeGasCostOverride
from .gas.rates_previous_consumption_override import EDFEnergyGasPreviousConsumptionOverrideRates
from .gas.current_total_consumption_cubic_meters import EDFEnergyCurrentTotalGasConsumptionCubicMeters
from .gas.current_total_consumption_kwh import EDFEnergyCurrentTotalGasConsumptionKwh
from .cost_tracker.cost_tracker import EDFEnergyCostTrackerSensor
from .cost_tracker.cost_tracker_week import EDFEnergyCostTrackerWeekSensor
from .cost_tracker.cost_tracker_month import EDFEnergyCostTrackerMonthSensor
from .diagnostics_entities.account_data_last_retrieved import EDFEnergyAccountDataLastRetrieved
from .diagnostics_entities.auth_token_expiry import EDFEnergyAuthTokenExpiry
from .diagnostics_entities.gas_current_consumption_data_last_retrieved import EDFEnergyGasCurrentConsumptionDataLastRetrieved
from .diagnostics_entities.electricity_rates_data_last_retrieved import EDFEnergyElectricityCurrentRatesDataLastRetrieved
from .diagnostics_entities.electricity_previous_consumption_and_rates_data_last_retrieved import EDFEnergyElectricityPreviousConsumptionAndRatesDataLastRetrieved
from .diagnostics_entities.electricity_standing_charge_data_last_retrieved import EDFEnergyElectricityCurrentStandingChargeDataLastRetrieved
from .diagnostics_entities.intelligent_dispatches_data_last_retrieved import EDFEnergyIntelligentDispatchesDataLastRetrieved
from .diagnostics_entities.intelligent_settings_data_last_retrieved import EDFEnergyIntelligentSettingsDataLastRetrieved
from .diagnostics_entities.electricity_current_consumption_data_last_retrieved import EDFEnergyElectricityCurrentConsumptionDataLastRetrieved
from .diagnostics_entities.gas_previous_consumption_and_rates_data_last_retrieved import EDFEnergyGasPreviousConsumptionAndRatesDataLastRetrieved
from .diagnostics_entities.gas_rates_data_last_retrieved import EDFEnergyGasCurrentRatesDataLastRetrieved
from .diagnostics_entities.gas_standing_charge_data_last_retrieved import EDFEnergyGasCurrentStandingChargeDataLastRetrieved
from .api_client.intelligent_device import IntelligentDevice
from .intelligent.current_state import EDFEnergyIntelligentCurrentState
from .intelligent import get_intelligent_features
from .sunday_saver.sensor import EDFEnergySundaySaverStartSensor, EDFEnergySundaySaverEndSensor
from .events.sensor import EDFEnergyEventFreeStartSensor, EDFEnergyEventFreeEndSensor

from .utils.debug_overrides import async_get_meter_debug_override

from .coordinators.current_consumption import async_create_current_consumption_coordinator
from .coordinators.gas_rates import async_setup_gas_rates_coordinator
from .coordinators.previous_consumption_and_rates import async_create_previous_consumption_and_rates_coordinator
from .coordinators.electricity_standing_charges import async_setup_electricity_standing_charges_coordinator
from .coordinators.gas_standing_charges import async_setup_gas_standing_charges_coordinator
from .coordinators.intelligent_device import IntelligentDeviceCoordinatorResult

from .api_client.intelligent_device import IntelligentDevice

from .api_client import EDFEnergyApiClient
from .utils.tariff_cache import async_get_cached_tariff_total_unique_rates, async_save_cached_tariff_total_unique_rates
from .utils.rate_information import get_peak_type, get_unique_rates, has_peak_rates

from .utils import (Tariff, get_active_tariff)
from .utils.repairs import safe_repair_key
from .const import (
  CONFIG_COST_TRACKER_MPAN,
  CONFIG_ACCOUNT_ID,
  CONFIG_COST_TRACKER_TARGET_ENTITY_ID,
  CONFIG_KIND,
  CONFIG_KIND_ACCOUNT,
  CONFIG_KIND_COST_TRACKER,
  CONFIG_KIND_TARIFF_COMPARISON,
  CONFIG_MAIN_INTELLIGENT_RATE_MODE,
  CONFIG_MAIN_INTELLIGENT_RATE_MODE_PLANNED_AND_STARTED_DISPATCHES,
  CONFIG_MAIN_INTELLIGENT_SETTINGS,
  CONFIG_MAIN_MANUAL_TARIFF_RATES,
  CONFIG_MAIN_PRICE_CAP_SETTINGS,
  CONFIG_TARIFF_COMPARISON_MPAN_MPRN,
  DATA_ACCOUNT_COORDINATOR,
  DATA_INTELLIGENT_DEVICES,
  DATA_INTELLIGENT_DISPATCHES_COORDINATOR,
  DATA_INTELLIGENT_SETTINGS_COORDINATOR,
  DATA_PREVIOUS_CONSUMPTION_COORDINATOR_KEY,
  DATA_SUNDAY_SAVER_COORDINATOR,
  DATA_EVENT_FREE_ELECTRICITY_COORDINATOR,
  DEFAULT_CALORIFIC_VALUE,
  DOMAIN,

  CONFIG_MAIN_CALORIFIC_VALUE,
  CONFIG_MAIN_ELECTRICITY_PRICE_CAP,
  CONFIG_MAIN_GAS_PRICE_CAP,

  DATA_ELECTRICITY_RATES_COORDINATOR_KEY,
  DATA_CLIENT,
  DATA_ACCOUNT
)

_LOGGER = logging.getLogger(__name__)

async def get_unique_electricity_rates(hass, client: EDFEnergyApiClient, tariff: Tariff):
  total_unique_rates = await async_get_cached_tariff_total_unique_rates(hass, tariff.code)
  if total_unique_rates is None:
    _LOGGER.info(f"Retrieving electricity rates '{tariff.code}' to determine number of unique rates")

    current_date = now()
    # Look at yesterdays rates so we have a complete picture
    period_from = current_date.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
    period_to = period_from + timedelta(days=1)
    rates = await client.async_get_electricity_rates(tariff.product, tariff.code, True, period_from, period_to)
    if not rates:
      _LOGGER.warning(f"Failed to retrieve rates for tariff '{tariff.product}/{tariff.code}' to determine unique rates. Defaulting to single unique rate.")
      return 1
    
    total_unique_rates = len(get_unique_rates(current_date - timedelta(days=1), rates))
    if total_unique_rates < 1:
      raise Exception(f"Unique rates for tariff '{tariff.code}' is less than 1")

    await async_save_cached_tariff_total_unique_rates(hass, tariff.code, total_unique_rates)

  return total_unique_rates

async def async_setup_entry(hass, entry, async_add_entities):
  """Setup sensors based on our entry"""

  config = dict(entry.data)

  if config[CONFIG_KIND] == CONFIG_KIND_ACCOUNT:
    await async_setup_default_sensors(hass, config, async_add_entities)

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
      "refresh_previous_consumption_data",
      vol.All(
        cv.make_entity_service_schema(
          {
            vol.Optional("start_time"): str,
          },
          extra=vol.ALLOW_EXTRA,
        ),
      ),
      "async_refresh_previous_consumption_data"
    )

  elif config[CONFIG_KIND] == CONFIG_KIND_COST_TRACKER:
    await async_setup_cost_sensors(hass, entry, config, async_add_entities)

    platform = entity_platform.async_get_current_platform()
    platform.async_register_entity_service(
      "update_cost_tracker",
      vol.All(
        cv.make_entity_service_schema(
          {
            vol.Required("is_tracking_enabled"): bool,
          },
          extra=vol.ALLOW_EXTRA,
        ),
      ),
      "async_update_cost_tracker_config"
    )

    platform.async_register_entity_service(
      "reset_cost_tracker",
      vol.All(
        cv.make_entity_service_schema(
          {},
          extra=vol.ALLOW_EXTRA,
        ),
      ),
      "async_reset_cost_tracker"
    )

    platform.async_register_entity_service(
      "adjust_accumulative_cost_tracker",
      vol.All(
        cv.make_entity_service_schema(
          {
            vol.Required("date"): cv.date,
            vol.Required("consumption"): cv.positive_float,
            vol.Required("cost"): cv.positive_float,
          },
          extra=vol.ALLOW_EXTRA,
        ),
      ),
      "async_adjust_accumulative_cost_tracker"
    )

    platform.async_register_entity_service(
      "adjust_cost_tracker",
      vol.All(
        cv.make_entity_service_schema(
          {
            vol.Required("datetime"): cv.datetime,
            vol.Required("consumption"): cv.positive_float,
          },
          extra=vol.ALLOW_EXTRA,
        ),
      ),
      "async_adjust_cost_tracker"
    )

  elif config[CONFIG_KIND] == CONFIG_KIND_TARIFF_COMPARISON:
    await async_setup_tariff_comparison_sensors(hass, entry, config, async_add_entities)

async def async_setup_default_sensors(hass: HomeAssistant, config, async_add_entities):
  account_id = config[CONFIG_ACCOUNT_ID]
  
  client = hass.data[DOMAIN][account_id][DATA_CLIENT]

  account_result = hass.data[DOMAIN][account_id][DATA_ACCOUNT]
  account_info = account_result.account if account_result is not None else None

  entities = [
    EDFEnergyAccountDataLastRetrieved(hass, hass.data[DOMAIN][account_id][DATA_ACCOUNT_COORDINATOR], account_id),
    EDFEnergyAuthTokenExpiry(hass, account_id),
  ]

  sunday_saver_coordinator = hass.data[DOMAIN][account_id].get(DATA_SUNDAY_SAVER_COORDINATOR.format(account_id))
  if sunday_saver_coordinator is not None:
    entities.append(EDFEnergySundaySaverStartSensor(hass, sunday_saver_coordinator, account_id))
    entities.append(EDFEnergySundaySaverEndSensor(hass, sunday_saver_coordinator, account_id))

  event_coordinator = hass.data[DOMAIN][account_id].get(DATA_EVENT_FREE_ELECTRICITY_COORDINATOR.format(account_id))
  if event_coordinator is not None:
    entities.append(EDFEnergyEventFreeStartSensor(hass, event_coordinator, account_id))
    entities.append(EDFEnergyEventFreeEndSensor(hass, event_coordinator, account_id))

  intelligent_result: IntelligentDeviceCoordinatorResult = hass.data[DOMAIN][account_id][DATA_INTELLIGENT_DEVICES] if DATA_INTELLIGENT_DEVICES in hass.data[DOMAIN][account_id] else None
  intelligent_devices: list[IntelligentDevice] = (intelligent_result.devices or []) if intelligent_result is not None else []

  for intelligent_device in intelligent_devices:
    intelligent_dispatches_coordinator = hass.data[DOMAIN][account_id][DATA_INTELLIGENT_DISPATCHES_COORDINATOR.format(intelligent_device.id)] if DATA_INTELLIGENT_DISPATCHES_COORDINATOR.format(intelligent_device.id) in hass.data[DOMAIN][account_id] else None
    if intelligent_dispatches_coordinator is not None:
      entities.append(EDFEnergyIntelligentDispatchesDataLastRetrieved(hass, intelligent_dispatches_coordinator, account_id, intelligent_device))

      intelligent_features = get_intelligent_features(intelligent_device.provider)
      if intelligent_features.current_state_supported:
        entities.append(EDFEnergyIntelligentCurrentState(hass, intelligent_dispatches_coordinator, intelligent_device, account_id))
                      
    intelligent_settings_coordinator = hass.data[DOMAIN][account_id][DATA_INTELLIGENT_SETTINGS_COORDINATOR.format(intelligent_device.id)] if DATA_INTELLIGENT_SETTINGS_COORDINATOR.format(intelligent_device.id) in hass.data[DOMAIN][account_id] else None
    if intelligent_settings_coordinator is not None:
      entities.append(EDFEnergyIntelligentSettingsDataLastRetrieved(hass, intelligent_settings_coordinator, account_id, intelligent_device))

  registry = er.async_get(hass)
  entity_ids_to_migrate = []

  now = utcnow()

  if len(account_info["electricity_meter_points"]) > 0:
    electricity_price_cap = None
    if (CONFIG_MAIN_PRICE_CAP_SETTINGS in config and CONFIG_MAIN_ELECTRICITY_PRICE_CAP in config[CONFIG_MAIN_PRICE_CAP_SETTINGS]):
      electricity_price_cap = config[CONFIG_MAIN_PRICE_CAP_SETTINGS][CONFIG_MAIN_ELECTRICITY_PRICE_CAP]

    for point in account_info["electricity_meter_points"]:
      # We only care about points that have active agreements
      electricity_tariff = get_active_tariff(now, point["agreements"])
      if electricity_tariff is not None:
        for meter in point["meters"]:
          mpan = point["mpan"]
          serial_number = meter["serial_number"]

          _LOGGER.info(f'Adding electricity meter; mpan: {mpan}; serial number: {serial_number}')

          electricity_rate_coordinator = hass.data[DOMAIN][account_id][DATA_ELECTRICITY_RATES_COORDINATOR_KEY.format(mpan, serial_number)]
          electricity_standing_charges_coordinator = await async_setup_electricity_standing_charges_coordinator(hass, account_id, mpan, serial_number, config.get(CONFIG_MAIN_MANUAL_TARIFF_RATES))

          entities.append(EDFEnergyElectricityCurrentRate(hass, electricity_rate_coordinator, meter, point, electricity_price_cap, account_id))
          entities.append(EDFEnergyElectricityPreviousRate(hass, electricity_rate_coordinator, meter, point))
          entities.append(EDFEnergyElectricityNextRate(hass, electricity_rate_coordinator, meter, point))
          entities.append(EDFEnergyElectricityCurrentStandingCharge(hass, electricity_standing_charges_coordinator, meter, point))
          entities.append(EDFEnergyElectricityCurrentRatesDataLastRetrieved(hass, electricity_rate_coordinator, meter, point))
          entities.append(EDFEnergyElectricityCurrentStandingChargeDataLastRetrieved(hass, electricity_standing_charges_coordinator, meter, point))

          debug_override = await async_get_meter_debug_override(hass, mpan, serial_number)
          intelligent_rate_mode = (config[CONFIG_MAIN_INTELLIGENT_SETTINGS][CONFIG_MAIN_INTELLIGENT_RATE_MODE] 
                                   if CONFIG_MAIN_INTELLIGENT_SETTINGS in config and CONFIG_MAIN_INTELLIGENT_RATE_MODE in config[CONFIG_MAIN_INTELLIGENT_SETTINGS] 
                                   else CONFIG_MAIN_INTELLIGENT_RATE_MODE_PLANNED_AND_STARTED_DISPATCHES)
          previous_consumption_coordinator = await async_create_previous_consumption_and_rates_coordinator(
            hass,
            account_id,
            client,
            mpan,
            serial_number,
            True,
            meter["is_smart_meter"],
            intelligent_rate_mode,
            debug_override.tariff if debug_override is not None else None,
            config.get(CONFIG_MAIN_MANUAL_TARIFF_RATES)
          )
          entities.append(EDFEnergyPreviousAccumulativeElectricityConsumption(hass, client, previous_consumption_coordinator, account_id, meter, point))
          entities.append(EDFEnergyPreviousAccumulativeElectricityCost(hass, previous_consumption_coordinator, meter, point))
          entities.append(EDFEnergyElectricityPreviousConsumptionAndRatesDataLastRetrieved(hass, previous_consumption_coordinator, meter, point))

          # Create a peak override for each available peak type for our tariff
          total_unique_rates = await get_unique_electricity_rates(hass, client, electricity_tariff if debug_override is None or debug_override.tariff is None else debug_override.tariff)
          for unique_rate_index in range(0, total_unique_rates):
            peak_type = get_peak_type(total_unique_rates, unique_rate_index)
            if peak_type is not None:
              entities.append(EDFEnergyPreviousAccumulativeElectricityConsumption(hass, client, previous_consumption_coordinator, account_id, meter, point, peak_type))
              entities.append(EDFEnergyPreviousAccumulativeElectricityCost(hass, previous_consumption_coordinator, meter, point, peak_type))

      else:
        for meter in point["meters"]:
          _LOGGER.info(f'Skipping electricity meter due to no active agreement; mpan: {point["mpan"]}; serial number: {meter["serial_number"]}')
        _LOGGER.info(f'agreements: {point["agreements"]}')
  else:
    _LOGGER.info('No electricity meters available')

  if len(account_info["gas_meter_points"]) > 0:

    calorific_value = DEFAULT_CALORIFIC_VALUE
    if CONFIG_MAIN_CALORIFIC_VALUE in config:
      calorific_value = config[CONFIG_MAIN_CALORIFIC_VALUE]

    gas_price_cap = None
    if (CONFIG_MAIN_PRICE_CAP_SETTINGS in config and CONFIG_MAIN_GAS_PRICE_CAP in config[CONFIG_MAIN_PRICE_CAP_SETTINGS]):
      gas_price_cap = config[CONFIG_MAIN_PRICE_CAP_SETTINGS][CONFIG_MAIN_GAS_PRICE_CAP]

    for point in account_info["gas_meter_points"]:
      # We only care about points that have active agreements
      gas_tariff = get_active_tariff(now, point["agreements"])
      if gas_tariff is not None:
        for meter in point["meters"]:
          mprn = point["mprn"]
          serial_number = meter["serial_number"]

          _LOGGER.info(f'Adding gas meter; mprn: {mprn}; serial number: {serial_number}')

          gas_rate_coordinator = await async_setup_gas_rates_coordinator(hass, account_id, client, mprn, serial_number)
          gas_standing_charges_coordinator = await async_setup_gas_standing_charges_coordinator(hass, account_id, mprn, serial_number)

          entities.append(EDFEnergyGasCurrentRate(hass, gas_rate_coordinator, meter, point, gas_price_cap))
          entities.append(EDFEnergyGasPreviousRate(hass, gas_rate_coordinator, meter, point))
          entities.append(EDFEnergyGasNextRate(hass, gas_rate_coordinator, meter, point))
          entities.append(EDFEnergyGasCurrentStandingCharge(hass, gas_standing_charges_coordinator, meter, point))
          entities.append(EDFEnergyGasCurrentRatesDataLastRetrieved(hass, gas_rate_coordinator, meter, point))
          entities.append(EDFEnergyGasCurrentStandingChargeDataLastRetrieved(hass, gas_standing_charges_coordinator, meter, point))

          debug_override = await async_get_meter_debug_override(hass, mprn, serial_number)
          intelligent_rate_mode = (config[CONFIG_MAIN_INTELLIGENT_SETTINGS][CONFIG_MAIN_INTELLIGENT_RATE_MODE] 
                                   if CONFIG_MAIN_INTELLIGENT_SETTINGS in config and CONFIG_MAIN_INTELLIGENT_RATE_MODE in config[CONFIG_MAIN_INTELLIGENT_SETTINGS] 
                                   else CONFIG_MAIN_INTELLIGENT_RATE_MODE_PLANNED_AND_STARTED_DISPATCHES)
          previous_consumption_coordinator = await async_create_previous_consumption_and_rates_coordinator(
            hass,
            account_id,
            client,
            mprn,
            serial_number,
            False,
            None,
            intelligent_rate_mode,
            debug_override.tariff if debug_override is not None and debug_override.tariff is not None else None
          )
          entities.append(EDFEnergyPreviousAccumulativeGasConsumptionCubicMeters(hass, client, previous_consumption_coordinator, account_id, meter, point, calorific_value))
          entities.append(EDFEnergyPreviousAccumulativeGasConsumptionKwh(hass, previous_consumption_coordinator, meter, point, calorific_value))
          entities.append(EDFEnergyPreviousAccumulativeGasCost(hass, previous_consumption_coordinator, meter, point, calorific_value))
          entities.append(EDFEnergyGasPreviousConsumptionAndRatesDataLastRetrieved(hass, previous_consumption_coordinator, meter, point))

          entity_ids_to_migrate.append({
            "old": f"edf_energy_gas_{serial_number}_{mprn}_previous_accumulative_consumption",
            "new": f"edf_energy_gas_{serial_number}_{mprn}_previous_accumulative_consumption_m3"
          })

      else:
        for meter in point["meters"]:
          _LOGGER.info(f'Skipping gas meter due to no active agreement; mprn: {point["mprn"]}; serial number: {meter["serial_number"]}')
        _LOGGER.info(f'agreements: {point["agreements"]}')
  else:
    _LOGGER.info('No gas meters available')

  # Migrate entity ids that might have changed
  # for item in entity_ids_to_migrate:
  #   entity_id = registry.async_get_entity_id("sensor", DOMAIN, item["old"])
  #   if entity_id is not None:
  #     try:
  #       _LOGGER.info(f'Migrating entity id and unique id for {item["old"]} to {item["new"]}')
  #       registry.async_update_entity(entity_id, new_entity_id=f'sensor.{item["new"]}'.lower(), new_unique_id=item["new"])
  #     except Exception as e:
  #       _LOGGER.warning(f'Failed to migrate entity id and unique id for {item["old"]} to {item["new"]} - {e}')

  async_add_entities(entities)

async def async_setup_cost_sensors(hass: HomeAssistant, entry, config, async_add_entities):
  account_id = config[CONFIG_ACCOUNT_ID]
  account_result = hass.data[DOMAIN][account_id][DATA_ACCOUNT]
  account_info = account_result.account if account_result is not None else None
  client = hass.data[DOMAIN][account_id][DATA_CLIENT]

  mpan = config[CONFIG_COST_TRACKER_MPAN]

  registry = er.async_get(hass)

  now = utcnow()
  for point in account_info["electricity_meter_points"]:
    tariff = get_active_tariff(now, point["agreements"])
    if tariff is not None:
      # For backwards compatibility, pick the first applicable meter
      if point["mpan"] == mpan or mpan is None:
        for meter in point["meters"]:
          serial_number = meter["serial_number"]
          coordinator = hass.data[DOMAIN][account_id][DATA_ELECTRICITY_RATES_COORDINATOR_KEY.format(mpan, serial_number)]

          device_registry = dr.async_get(hass)
          entity_registry = er.async_get(hass)

          source_entity_id = config[CONFIG_COST_TRACKER_TARGET_ENTITY_ID]

          device_id = None
          if source_entity_id:
              entity = entity_registry.async_get(source_entity_id)
              if entity:
                  device_id = entity.device_id

          device_entry = None
          if device_id is not None:
            device_entry = device_registry.async_get(device_id)

          sensor = EDFEnergyCostTrackerSensor(hass, coordinator, entry, config, device_entry)
          sensor_entity_id = registry.async_get_entity_id("sensor", DOMAIN, sensor.unique_id)

          entities = [
            sensor,
            EDFEnergyCostTrackerWeekSensor(hass, entry, config, device_entry, sensor_entity_id if sensor_entity_id is not None else sensor.entity_id),
            EDFEnergyCostTrackerMonthSensor(hass, entry, config, device_entry, sensor_entity_id if sensor_entity_id is not None else sensor.entity_id),
          ]
          
          debug_override = await async_get_meter_debug_override(hass, mpan, serial_number)
          total_unique_rates = await get_unique_electricity_rates(hass, client, tariff if debug_override is None or debug_override.tariff is None else debug_override.tariff)
          if has_peak_rates(total_unique_rates):
            for unique_rate_index in range(0, total_unique_rates):
              peak_type = get_peak_type(total_unique_rates, unique_rate_index)
              if peak_type is not None:
                peak_sensor = EDFEnergyCostTrackerSensor(hass, coordinator, entry, config, device_entry, peak_type)
                peak_sensor_entity_id = registry.async_get_entity_id("sensor", DOMAIN, peak_sensor.unique_id)
                
                entities.append(peak_sensor)
                entities.append(EDFEnergyCostTrackerWeekSensor(hass, entry, config, device_entry, peak_sensor_entity_id if peak_sensor_entity_id is not None else f"sensor.{peak_sensor.unique_id}", peak_type))
                entities.append(EDFEnergyCostTrackerMonthSensor(hass, entry, config, device_entry, peak_sensor_entity_id if peak_sensor_entity_id is not None else f"sensor.{peak_sensor.unique_id}", peak_type))

          async_add_entities(entities)
          break

async def async_setup_tariff_comparison_sensors(hass: HomeAssistant, entry, config, async_add_entities):
  account_id = config[CONFIG_ACCOUNT_ID]
  account_result = hass.data[DOMAIN][account_id][DATA_ACCOUNT]
  account_info = account_result.account if account_result is not None else None
  client = hass.data[DOMAIN][account_id][DATA_CLIENT]

  mpan_mprn = config[CONFIG_TARIFF_COMPARISON_MPAN_MPRN]

  calorific_value = DEFAULT_CALORIFIC_VALUE
  config_entries = hass.config_entries.async_entries(DOMAIN, include_ignore=False)
  for entry in config_entries:
    config_entry_data = dict(entry.data)

    if config_entry_data[CONFIG_KIND] == CONFIG_KIND_ACCOUNT and config_entry_data[CONFIG_ACCOUNT_ID] == account_id and CONFIG_MAIN_CALORIFIC_VALUE in config_entry_data:
      calorific_value = config_entry_data[CONFIG_MAIN_CALORIFIC_VALUE]

  now = utcnow()
  for point in account_info["electricity_meter_points"]:
    tariff = get_active_tariff(now, point["agreements"])
    if tariff is not None:
      if point["mpan"] == mpan_mprn:
        for meter in point["meters"]:
          serial_number = meter["serial_number"]
          coordinator = hass.data[DOMAIN][account_id][DATA_PREVIOUS_CONSUMPTION_COORDINATOR_KEY.format(mpan_mprn, serial_number)]
          entities = [
            EDFEnergyPreviousAccumulativeElectricityCostOverride(hass, account_id, coordinator, client, meter, point, config),
            EDFEnergyElectricityPreviousConsumptionOverrideRates(hass, meter, point, config)
          ]
          
          async_add_entities(entities)
          break

  now = utcnow()
  for point in account_info["gas_meter_points"]:
    tariff = get_active_tariff(now, point["agreements"])
    if tariff is not None:
      if point["mprn"] == mpan_mprn:
        for meter in point["meters"]:
          serial_number = meter["serial_number"]
          coordinator = hass.data[DOMAIN][account_id][DATA_PREVIOUS_CONSUMPTION_COORDINATOR_KEY.format(mpan_mprn, serial_number)]
          entities = [
            EDFEnergyPreviousAccumulativeGasCostOverride(hass, account_id, coordinator, client, meter, point, calorific_value, config),
            EDFEnergyGasPreviousConsumptionOverrideRates(hass, meter, point, config)
          ]
          
          async_add_entities(entities)
          break
