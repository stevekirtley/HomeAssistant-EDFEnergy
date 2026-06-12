import logging
import os
from datetime import datetime, timedelta

from homeassistant.components.frontend import async_register_built_in_panel
from homeassistant.components.http import StaticPathConfig
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.components.recorder import get_instance
from homeassistant.util.dt import (utcnow)
from homeassistant.const import (
    EVENT_HOMEASSISTANT_STOP
)
from homeassistant.helpers import (
  issue_registry as ir
)

from homeassistant.helpers.helper_integration import (
    async_remove_helper_config_entry_from_source_device,
)

from .coordinators.account import AccountCoordinatorResult, async_setup_account_info_coordinator
from .coordinators.intelligent_dispatches import IntelligentDispatchesCoordinatorResult, async_setup_intelligent_dispatches_coordinator
from .coordinators.intelligent_settings import async_setup_intelligent_settings_coordinator
from .coordinators.electricity_rates import async_setup_electricity_rates_coordinator
from .coordinators.sunday_saver import async_setup_sunday_saver_coordinator
from .coordinators.event_free_electricity import async_setup_event_free_electricity_coordinator
from .coordinators.free_electricity_sessions import async_setup_free_electricity_sessions_coordinator
from .statistics import get_statistic_ids_to_remove
from .intelligent import get_intelligent_features, mock_intelligent_devices
from .config.tariff_comparison import async_migrate_tariff_comparison_config

from .config.main import async_migrate_main_config
from .config.cost_tracker import async_migrate_cost_tracker_config
from .utils import get_active_tariff, get_tariff_parts
from .utils.debug_overrides import async_get_account_debug_override, async_get_meter_debug_override
from .utils.error import api_exception_to_string
from .storage.account import async_load_cached_account, async_save_cached_account
from .storage.intelligent_device import async_load_cached_intelligent_devices, async_save_cached_intelligent_devices
from .storage.intelligent_dispatches import async_load_cached_intelligent_dispatches
from .storage.intelligent_dispatches_history import IntelligentDispatchesHistory, async_load_cached_intelligent_dispatches_history
from .api_client.intelligent_dispatches import IntelligentDispatches
from .discovery import DiscoveryManager
from .coordinators.intelligent_device import IntelligentDeviceCoordinatorResult, async_setup_intelligent_devices_coordinator

from .utils.repairs import safe_repair_key

from .const import (
  CONFIG_COST_TRACKER_TARGET_ENTITY_ID,
  CONFIG_DEFAULT_MINIMUM_DISPATCH_DURATION_IN_MINUTES,
  CONFIG_MAIN_AUTO_DISCOVER_COST_TRACKERS,
  CONFIG_MAIN_FAVOUR_DIRECT_DEBIT_RATES,
  CONFIG_KIND,
  CONFIG_KIND_ACCOUNT,
  CONFIG_KIND_ROLLING_TARGET_RATE,
  CONFIG_KIND_TARIFF_COMPARISON,
  CONFIG_KIND_COST_TRACKER,
  CONFIG_KIND_TARGET_RATE,
  CONFIG_MAIN_INTELLIGENT_MANUAL_DISPATCHES,
  CONFIG_MAIN_INTELLIGENT_MINIMUM_DISPATCH_DURATION_IN_MINUTES,
  CONFIG_MAIN_INTELLIGENT_RATE_MODE,
  CONFIG_MAIN_INTELLIGENT_RATE_MODE_PLANNED_AND_STARTED_DISPATCHES,
  CONFIG_MAIN_INTELLIGENT_SETTINGS,
  CONFIG_MAIN_MANUAL_TARIFF_RATES,
  CONFIG_MAIN_OLD_API_KEY,
  CONFIG_MAIN_PRICE_CAP_SETTINGS,
  CONFIG_VERSION,
  DATA_DISCOVERY_MANAGER,
  DATA_INTELLIGENT_DEVICES,
  DATA_INTELLIGENT_DISPATCHES,
  DATA_PREVIOUS_CONSUMPTION_COORDINATOR_KEY,
  DATA_SUNDAY_SAVER,
  DATA_SUNDAY_SAVER_COORDINATOR,
  DATA_FREE_ELECTRICITY_SESSIONS_COORDINATOR,
  DOMAIN,

  CONFIG_MAIN_API_KEY,
  CONFIG_MAIN_FOOTBALL_FREE_ELECTRICITY,
  CONFIG_MAIN_REFRESH_TOKEN,
  CONFIG_ACCOUNT_ID,
  CONFIG_MAIN_ELECTRICITY_PRICE_CAP,
  CONFIG_MAIN_GAS_PRICE_CAP,

  DATA_CLIENT,
  DATA_ELECTRICITY_RATES_COORDINATOR_KEY,
  DATA_ACCOUNT,
  REFRESH_RATE_IN_MINUTES_INTELLIGENT,
  REPAIR_ACCOUNT_NOT_FOUND,
  REPAIR_INVALID_API_KEY,
  REPAIR_TARGET_RATE_NOT_SUPPORTED,
  REPAIR_UNIQUE_RATES_CHANGED_KEY,
  REPAIR_UNKNOWN_INTELLIGENT_PROVIDER,
  SERVICE_SET_FOOTBALL_FREE_ELECTRICITY,
)

ACCOUNT_PLATFORMS = ["sensor", "binary_sensor", "number", "switch", "text", "time", "event", "select", "calendar"]
COST_TRACKER_PLATFORMS = ["sensor"]
TARIFF_COMPARISON_PLATFORMS = ["sensor"]

from .api_client import ApiException, AuthenticationException, EDFEnergyApiClient

_LOGGER = logging.getLogger(__name__)

SCAN_INTERVAL = timedelta(minutes=1)

async def async_remove_config_entry_device(
  hass, config_entry, device_entry
) -> bool:
  """Remove a config entry from a device."""
  return True

async def async_migrate_entry(hass, config_entry):
  """Migrate old entry."""
  if (config_entry.version < CONFIG_VERSION):
    _LOGGER.debug("Migrating from version %s", config_entry.version)

    new_data = dict(config_entry.data)
    title = config_entry.title

    # Move to reconfiguration from options
    if (config_entry.version <= 8 and new_data is not None and config_entry.options is not None):
      new_data.update(config_entry.options)

    if CONFIG_MAIN_API_KEY in new_data or CONFIG_MAIN_OLD_API_KEY in new_data or (CONFIG_KIND in new_data and new_data[CONFIG_KIND] == CONFIG_KIND_ACCOUNT):
      new_data = await async_migrate_main_config(config_entry.version, new_data)
      title = new_data[CONFIG_ACCOUNT_ID]
    elif CONFIG_KIND in new_data and new_data[CONFIG_KIND] == CONFIG_KIND_COST_TRACKER:
      new_data = await async_migrate_cost_tracker_config(config_entry.version, new_data, hass.config_entries.async_entries)

      if config_entry.version < 9:
        async_remove_helper_config_entry_from_source_device(
          hass,
          helper_config_entry_id=config_entry.entry_id,
          source_device_id=new_data[CONFIG_COST_TRACKER_TARGET_ENTITY_ID],
        )

    elif CONFIG_KIND in new_data and new_data[CONFIG_KIND] == CONFIG_KIND_TARIFF_COMPARISON:
      new_data = await async_migrate_tariff_comparison_config(config_entry.version, new_data, hass.config_entries.async_entries)
    
    hass.config_entries.async_update_entry(config_entry, title=title, data=new_data, options={}, version=CONFIG_VERSION)

    _LOGGER.debug("Migration to version %s successful", config_entry.version)

  return True

async def _async_close_client(hass, account_id: str):
  if account_id in hass.data[DOMAIN]:
    if DATA_CLIENT in hass.data[DOMAIN][account_id]:
      _LOGGER.debug('Closing client...')
      client: EDFEnergyApiClient = hass.data[DOMAIN][account_id][DATA_CLIENT]
      await client.async_close()
      _LOGGER.debug('Client closed.')

async def async_setup_entry(hass, entry):
  """This is called from the config flow."""
  hass.data.setdefault(DOMAIN, {})

  if not hass.data[DOMAIN].get("_frontend_registered"):
    hass.data[DOMAIN]["_frontend_registered"] = True
    www_dir = os.path.join(os.path.dirname(__file__), "www")
    static_paths = []

    card_path = os.path.join(www_dir, "edf-energy-dispatches-card.js")
    if os.path.isfile(card_path):
      static_paths.append(StaticPathConfig("/edf_energy/edf-energy-dispatches-card.js", card_path, False))

    panel_path = os.path.join(www_dir, "edf-energy-panel.js")
    register_panel = os.path.isfile(panel_path)
    if register_panel:
      static_paths.append(StaticPathConfig("/edf_energy/edf-energy-panel.js", panel_path, False))

    if static_paths:
      await hass.http.async_register_static_paths(static_paths)

    if register_panel:
      try:
        async_register_built_in_panel(
          hass,
          "custom",
          sidebar_title="EDF Energy",
          sidebar_icon="mdi:ev-plug-type2",
          frontend_url_path="edf-energy",
          config={
            "_panel_custom": {
              "name": "edf-energy-panel",
              "js_url": "/edf_energy/edf-energy-panel.js",
              "embed_iframe": False,
              "trust_external": False,
            }
          },
          require_admin=False,
        )
      except ValueError:
        _LOGGER.debug("EDF Energy frontend panel already registered, skipping")

  config = dict(entry.data)

  account_id = config[CONFIG_ACCOUNT_ID]
  hass.data[DOMAIN].setdefault(account_id, {})

  if config[CONFIG_KIND] == CONFIG_KIND_ACCOUNT:
    await async_setup_dependencies(hass, entry, config)
    await hass.config_entries.async_forward_entry_setups(entry, ACCOUNT_PLATFORMS)

    async def async_close_connection(_) -> None:
      """Close client."""
      await _async_close_client(hass, account_id)

    entry.async_on_unload(
        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, async_close_connection)
    )

    # If the main account has been reloaded, then reload all other entries to make sure they're referencing
    # the correct references (e.g. rate coordinators)
    child_entries = hass.config_entries.async_entries(DOMAIN, include_ignore=False)
    for child_entry in child_entries:
      child_entry_config = dict(child_entry.data)

      if child_entry_config[CONFIG_KIND] != CONFIG_KIND_ACCOUNT and child_entry_config[CONFIG_ACCOUNT_ID] == account_id:
        await hass.config_entries.async_reload(child_entry.entry_id)

    if CONFIG_MAIN_AUTO_DISCOVER_COST_TRACKERS in config and config[CONFIG_MAIN_AUTO_DISCOVER_COST_TRACKERS] == True:
      discovery_manager = DiscoveryManager(hass, account_id)
      await discovery_manager.async_setup()
      hass.data[DOMAIN][account_id][DATA_DISCOVERY_MANAGER] = discovery_manager
  
  elif (config[CONFIG_KIND] == CONFIG_KIND_TARGET_RATE or config[CONFIG_KIND] == CONFIG_KIND_ROLLING_TARGET_RATE):
    ir.async_create_issue(
      hass,
      DOMAIN,
      REPAIR_TARGET_RATE_NOT_SUPPORTED,
      is_fixable=False,
      severity=ir.IssueSeverity.ERROR,
      translation_key="target_rate_not_supported",
    )
    
  elif config[CONFIG_KIND] == CONFIG_KIND_COST_TRACKER:
    if DOMAIN not in hass.data or account_id not in hass.data[DOMAIN] or DATA_ACCOUNT not in hass.data[DOMAIN][account_id]:
      raise ConfigEntryNotReady("Account has not been setup")
    
    now = utcnow()
    account_result = hass.data[DOMAIN][account_id][DATA_ACCOUNT]
    account_info = account_result.account if account_result is not None else None
    for point in account_info["electricity_meter_points"]:
      # We only care about points that have active agreements
      electricity_tariff = get_active_tariff(now, point["agreements"])
      if electricity_tariff is not None:
        for meter in point["meters"]:
          mpan = point["mpan"]
          serial_number = meter["serial_number"]
          previous_consumption_coordinator_key = DATA_ELECTRICITY_RATES_COORDINATOR_KEY.format(mpan, serial_number)
          if previous_consumption_coordinator_key not in hass.data[DOMAIN][account_id]:
            raise ConfigEntryNotReady(f"Electricity rates have not been setup for {mpan}/{serial_number}")

    await hass.config_entries.async_forward_entry_setups(entry, COST_TRACKER_PLATFORMS)
  
  elif config[CONFIG_KIND] == CONFIG_KIND_TARIFF_COMPARISON:
    if DOMAIN not in hass.data or account_id not in hass.data[DOMAIN] or DATA_ACCOUNT not in hass.data[DOMAIN][account_id]:
      raise ConfigEntryNotReady("Account has not been setup")
    
    now = utcnow()
    account_result = hass.data[DOMAIN][account_id][DATA_ACCOUNT]
    account_info = account_result.account if account_result is not None else None
    for point in account_info["electricity_meter_points"]:
      # We only care about points that have active agreements
      electricity_tariff = get_active_tariff(now, point["agreements"])
      if electricity_tariff is not None:
        for meter in point["meters"]:
          mpan = point["mpan"]
          serial_number = meter["serial_number"]
          previous_consumption_coordinator_key = DATA_PREVIOUS_CONSUMPTION_COORDINATOR_KEY.format(mpan, serial_number)
          if previous_consumption_coordinator_key not in hass.data[DOMAIN][account_id]:
            raise ConfigEntryNotReady(f"Previous electricity consumption has not been setup for {mpan}/{serial_number}")
          
    for point in account_info["gas_meter_points"]:
      # We only care about points that have active agreements
      gas_tariff = get_active_tariff(now, point["agreements"])
      if gas_tariff is not None:
        for meter in point["meters"]:
          mprn = point["mprn"]
          serial_number = meter["serial_number"]
          previous_consumption_coordinator_key = DATA_PREVIOUS_CONSUMPTION_COORDINATOR_KEY.format(mprn, serial_number)
          if previous_consumption_coordinator_key not in hass.data[DOMAIN][account_id]:
            raise ConfigEntryNotReady(f"Previous gas consumption has not been setup for {mprn}/{serial_number}")

    await hass.config_entries.async_forward_entry_setups(entry, TARIFF_COMPARISON_PLATFORMS)
  
  entry.async_on_unload(entry.add_update_listener(options_update_listener))

  return True

async def async_setup_dependencies(hass, entry, config):
  """Setup the coordinator and api client which will be shared by various entities"""
  account_id = config[CONFIG_ACCOUNT_ID]

  # Delete legacy issues
  ir.async_delete_issue(hass, DOMAIN, f"intelligent_manual_service_{account_id}")
  ir.async_delete_issue(hass, DOMAIN, REPAIR_UNIQUE_RATES_CHANGED_KEY.format(account_id))
  ir.async_delete_issue(hass, DOMAIN, REPAIR_ACCOUNT_NOT_FOUND.format(account_id))
  ir.async_delete_issue(hass, DOMAIN, REPAIR_INVALID_API_KEY.format(account_id))

  electricity_price_cap = None
  if (CONFIG_MAIN_PRICE_CAP_SETTINGS in config and CONFIG_MAIN_ELECTRICITY_PRICE_CAP in config[CONFIG_MAIN_PRICE_CAP_SETTINGS]):
    electricity_price_cap = config[CONFIG_MAIN_PRICE_CAP_SETTINGS][CONFIG_MAIN_ELECTRICITY_PRICE_CAP]

  gas_price_cap = None
  if (CONFIG_MAIN_PRICE_CAP_SETTINGS in config and CONFIG_MAIN_GAS_PRICE_CAP in config[CONFIG_MAIN_PRICE_CAP_SETTINGS]):
    gas_price_cap = config[CONFIG_MAIN_PRICE_CAP_SETTINGS][CONFIG_MAIN_GAS_PRICE_CAP]

  favour_direct_debit_rates = True
  if CONFIG_MAIN_FAVOUR_DIRECT_DEBIT_RATES in config:
    favour_direct_debit_rates = config[CONFIG_MAIN_FAVOUR_DIRECT_DEBIT_RATES]

  _LOGGER.info(f'electricity_price_cap: {electricity_price_cap}')
  _LOGGER.info(f'gas_price_cap: {gas_price_cap}')

  # Close any existing clients, as our new client may have changed
  await _async_close_client(hass, account_id)

  async def _async_persist_refresh_token(new_token: str):
    hass.config_entries.async_update_entry(entry, data={**entry.data, CONFIG_MAIN_REFRESH_TOKEN: new_token})

  client = EDFEnergyApiClient(config[CONFIG_MAIN_REFRESH_TOKEN], electricity_price_cap, gas_price_cap, favour_direct_debit_rates=favour_direct_debit_rates, on_token_refresh=_async_persist_refresh_token)
  hass.data[DOMAIN][account_id][DATA_CLIENT] = client

  # Delete any issues that may have been previously raised
  ir.async_delete_issue(hass, DOMAIN, safe_repair_key(REPAIR_UNIQUE_RATES_CHANGED_KEY, account_id))
  ir.async_delete_issue(hass, DOMAIN, safe_repair_key(REPAIR_ACCOUNT_NOT_FOUND, account_id))

  try:
    ir.async_delete_issue(hass, DOMAIN, safe_repair_key(REPAIR_INVALID_API_KEY, account_id))
    account_info = await client.async_get_account(config[CONFIG_ACCOUNT_ID])
    if (account_info is None):
      raise ConfigEntryNotReady(f"Failed to retrieve account information")
    await async_save_cached_account(hass, account_id, account_info)
  except Exception as e:
    if isinstance(e, ApiException) == False:
      raise

    if isinstance(e, AuthenticationException):
      raise ConfigEntryAuthFailed(f"Failed to retrieve account information: {api_exception_to_string(e)}")
    else:
      account_info = await async_load_cached_account(hass, account_id)
      if (account_info is None):
        raise ConfigEntryNotReady(f"Failed to retrieve account information: {api_exception_to_string(e)}")
      else:
        _LOGGER.warning(f"Using cached account information for {account_id} during startup. This data will be updated automatically when available.")

  hass.data[DOMAIN][account_id][DATA_ACCOUNT] = AccountCoordinatorResult(utcnow(), 1, account_info)

  device_registry = dr.async_get(hass)
  now = utcnow()

  if account_info is not None and len(account_info["gas_meter_points"]) > 0:
    for point in account_info["gas_meter_points"]:
      mprn = point["mprn"]
      for meter in point["meters"]:
        serial_number = meter["serial_number"]

        tariff = get_active_tariff(now, point["agreements"])
        if tariff is None:
          gas_device = device_registry.async_get_device(identifiers={(DOMAIN, f"gas_{serial_number}_{mprn}")})
          if gas_device is not None:
            _LOGGER.debug(f'Removed gas device {serial_number}/{mprn} due to no active tariff')
            device_registry.async_remove_device(gas_device.id)

        # Remove gas meter devices which had incorrect identifier
        gas_device = device_registry.async_get_device(identifiers={(DOMAIN, f"electricity_{serial_number}_{mprn}")})
        if gas_device is not None:
          device_registry.async_remove_device(gas_device.id)

  account_debug_override = await async_get_account_debug_override(hass, account_id)
  for point in account_info["electricity_meter_points"]:
    mpan = point["mpan"]
    electricity_tariff = get_active_tariff(now, point["agreements"])

    for meter in point["meters"]:  
      serial_number = meter["serial_number"]
      
      if electricity_tariff is None:
        _LOGGER.debug(f'Removed electricity device {serial_number}/{mpan} due to no active tariff')
        electricity_device = device_registry.async_get_device(identifiers={(DOMAIN, f"electricity_{serial_number}_{mpan}")})
        if electricity_device is not None:
          device_registry.async_remove_device(electricity_device.id)

  should_mock_intelligent_data = account_debug_override.mock_intelligent_controls if account_debug_override is not None else False
  if should_mock_intelligent_data:
    # Pick the first meter if we're mocking our intelligent data
    for point in account_info["electricity_meter_points"]:
      tariff = get_active_tariff(now, point["agreements"])
      if tariff is not None:
        for meter in point["meters"]:
          break

  await async_register_intelligent_devices(hass, config, now, account_id, should_mock_intelligent_data)

  region = None
  for point in account_info["electricity_meter_points"]:
    # We only care about points that have active agreements
    electricity_tariff = get_active_tariff(now, point["agreements"])
    if electricity_tariff is not None:
      if region is None:
        tariff_parts = get_tariff_parts(electricity_tariff.code)
        region = tariff_parts.region

      for meter in point["meters"]:
        mpan = point["mpan"]
        serial_number = meter["serial_number"]
        is_export_meter = meter["is_export"]
        is_smart_meter = meter["is_smart_meter"]
        override = await async_get_meter_debug_override(hass, mpan, serial_number)
        tariff_override = override.tariff if override is not None else None
        intelligent_rate_mode = (config[CONFIG_MAIN_INTELLIGENT_SETTINGS][CONFIG_MAIN_INTELLIGENT_RATE_MODE] 
                                 if CONFIG_MAIN_INTELLIGENT_SETTINGS in config and CONFIG_MAIN_INTELLIGENT_RATE_MODE in config[CONFIG_MAIN_INTELLIGENT_SETTINGS] 
                                 else CONFIG_MAIN_INTELLIGENT_RATE_MODE_PLANNED_AND_STARTED_DISPATCHES)
        
        minimum_dispatch_duration_in_minutes = (config[CONFIG_MAIN_INTELLIGENT_SETTINGS][CONFIG_MAIN_INTELLIGENT_MINIMUM_DISPATCH_DURATION_IN_MINUTES] 
                                 if CONFIG_MAIN_INTELLIGENT_SETTINGS in config and CONFIG_MAIN_INTELLIGENT_MINIMUM_DISPATCH_DURATION_IN_MINUTES in config[CONFIG_MAIN_INTELLIGENT_SETTINGS] 
                                 else CONFIG_DEFAULT_MINIMUM_DISPATCH_DURATION_IN_MINUTES)
        await async_setup_electricity_rates_coordinator(hass,
                                                        account_id,
                                                        mpan,
                                                        serial_number,
                                                        is_smart_meter,
                                                        is_export_meter,
                                                        intelligent_rate_mode,
                                                        tariff_override,
                                                        minimum_dispatch_duration_in_minutes,
                                                        config.get(CONFIG_MAIN_MANUAL_TARIFF_RATES))

  await async_setup_account_info_coordinator(hass, account_id, entry)
  await async_setup_sunday_saver_coordinator(hass, account_id)
  await async_setup_event_free_electricity_coordinator(hass, account_id)
  await async_setup_free_electricity_sessions_coordinator(hass, account_id, entry)

  _async_register_services(hass)


def _async_register_services(hass):
  """Register integration services (idempotent — safe to call per account entry)."""
  import voluptuous as vol
  from homeassistant.helpers import config_validation as cv

  if hass.services.has_service(DOMAIN, SERVICE_SET_FOOTBALL_FREE_ELECTRICITY):
    return

  async def _handle_set_football_free_electricity(call):
    enabled = call.data.get("enabled", False)
    account_id = call.data.get("account_id")
    for entry in hass.config_entries.async_entries(DOMAIN):
      if account_id is not None and entry.data.get(CONFIG_ACCOUNT_ID) != account_id:
        continue
      if entry.data.get("kind") != "account":
        continue
      hass.config_entries.async_update_entry(
        entry, options={**entry.options, CONFIG_MAIN_FOOTBALL_FREE_ELECTRICITY: enabled}
      )
      coordinator = hass.data.get(DOMAIN, {}).get(entry.data.get(CONFIG_ACCOUNT_ID), {}).get(
        DATA_FREE_ELECTRICITY_SESSIONS_COORDINATOR.format(entry.data.get(CONFIG_ACCOUNT_ID))
      )
      if coordinator is not None:
        await coordinator.async_request_refresh()

  hass.services.async_register(
    DOMAIN,
    SERVICE_SET_FOOTBALL_FREE_ELECTRICITY,
    _handle_set_football_free_electricity,
    schema=vol.Schema({
      vol.Required("enabled"): bool,
      vol.Optional("account_id"): cv.string,
    }),
  )


async def options_update_listener(hass, entry):
  """Handle options update."""
  await hass.config_entries.async_reload(entry.entry_id)

  if entry.data[CONFIG_KIND] == CONFIG_KIND_ACCOUNT:
    account_id = entry.data[CONFIG_ACCOUNT_ID]

    # If the main account has been reloaded, then reload all other entries to make sure they're referencing
    # the correct references (e.g. rate coordinators)
    child_entries = hass.config_entries.async_entries(DOMAIN, include_ignore=False)
    for child_entry in child_entries:
      child_entry_config = dict(child_entry.data)

      if child_entry_config[CONFIG_KIND] != CONFIG_KIND_ACCOUNT and child_entry_config[CONFIG_ACCOUNT_ID] == account_id:
        await hass.config_entries.async_reload(child_entry.entry_id)

async def async_unload_entry(hass, entry):
    """Unload a config entry."""

    unload_ok = False
    if entry.data[CONFIG_KIND] == CONFIG_KIND_ACCOUNT:
      unload_ok = await hass.config_entries.async_unload_platforms(entry, ACCOUNT_PLATFORMS)
      if unload_ok:
        account_id = entry.data[CONFIG_ACCOUNT_ID]
        await _async_close_client(hass, account_id)
        hass.data[DOMAIN].pop(account_id)

    elif entry.data[CONFIG_KIND] == CONFIG_KIND_TARIFF_COMPARISON:
      unload_ok = await hass.config_entries.async_unload_platforms(entry, TARIFF_COMPARISON_PLATFORMS)
    
    elif entry.data[CONFIG_KIND] == CONFIG_KIND_COST_TRACKER:
      unload_ok = await hass.config_entries.async_unload_platforms(entry, COST_TRACKER_PLATFORMS)

    return unload_ok

def setup(hass, config):
  """Set up is called when Home Assistant is loading our component."""

  def purge_invalid_external_statistic_ids(call):
    """Handle the service call."""

    account_id = None
    for entry in hass.config_entries.async_entries(DOMAIN, include_ignore=False):
      if CONFIG_KIND in entry.data and entry.data[CONFIG_KIND] == CONFIG_KIND_ACCOUNT:
        account_id = entry.data[CONFIG_ACCOUNT_ID]

    if account_id is None:
      raise Exception("Failed to find account id")
      
    account_result = hass.data[DOMAIN][account_id][DATA_ACCOUNT]
    account_info = account_result.account if account_result is not None else None
    
    external_statistic_ids_to_remove = get_statistic_ids_to_remove(utcnow(), account_info)

    if len(external_statistic_ids_to_remove) > 0:
      get_instance(hass).async_clear_statistics(external_statistic_ids_to_remove)
      _LOGGER.debug(f'Removing the following external statistics: {external_statistic_ids_to_remove}')

  hass.services.register(DOMAIN, "purge_invalid_external_statistic_ids", purge_invalid_external_statistic_ids)

  # Return boolean to indicate that initialization was successful.
  return True

async def async_register_intelligent_devices(hass, config: dict, now: datetime, account_id: str, should_mock_intelligent_data: bool):
  intelligent_manual_service_enabled = True
  intelligent_devices = []
  client: EDFEnergyApiClient = hass.data[DOMAIN][account_id][DATA_CLIENT]

  if should_mock_intelligent_data:
    # Load from cache to make sure everything works as intended
    intelligent_devices = await async_load_cached_intelligent_devices(hass, account_id)
    if intelligent_devices is None or len(intelligent_devices) < 1:
      intelligent_devices = mock_intelligent_devices()
  else:
    try:
      intelligent_devices = await client.async_get_intelligent_devices(account_id)
    except Exception as e:
      if isinstance(e, ApiException) == False:
        _LOGGER.error(f"Unexpected error fetching intelligent devices for {account_id}: {e}")

      intelligent_devices = await async_load_cached_intelligent_devices(hass, account_id)
      if (intelligent_devices is not None):
        _LOGGER.warning(f"Using cached intelligent device information for {account_id} during startup. This data will be updated automatically when available.")

  # Ensure intelligent_devices is always a list so downstream code can iterate safely
  if intelligent_devices is None:
    intelligent_devices = []

  hass.data[DOMAIN][account_id][DATA_INTELLIGENT_DEVICES] = IntelligentDeviceCoordinatorResult(now, 1, intelligent_devices)
  hass.data[DOMAIN][account_id][DATA_INTELLIGENT_DISPATCHES] = dict()

  if (CONFIG_MAIN_INTELLIGENT_SETTINGS not in config or
      CONFIG_MAIN_INTELLIGENT_MANUAL_DISPATCHES not in config[CONFIG_MAIN_INTELLIGENT_SETTINGS] or
      config[CONFIG_MAIN_INTELLIGENT_SETTINGS][CONFIG_MAIN_INTELLIGENT_MANUAL_DISPATCHES] == False):
    intelligent_manual_service_enabled = False

  await async_save_cached_intelligent_devices(hass, account_id, intelligent_devices)

  for intelligent_device in intelligent_devices:
    cached_dispatches = await async_load_cached_intelligent_dispatches(hass, account_id, intelligent_device.id)
    intelligent_dispatches_history = await async_load_cached_intelligent_dispatches_history(hass, intelligent_device.id)
    
    if cached_dispatches is not None:
      hass.data[DOMAIN][account_id][DATA_INTELLIGENT_DISPATCHES][intelligent_device.id] = IntelligentDispatchesCoordinatorResult(
        now - timedelta(hours=1),
        1,
        cached_dispatches,
        intelligent_dispatches_history,
        0,
        now - timedelta(hours=1)
      )
    else:
      hass.data[DOMAIN][account_id][DATA_INTELLIGENT_DISPATCHES][intelligent_device.id] = None

    intelligent_features = get_intelligent_features(intelligent_device.provider)  if intelligent_device is not None else None
    if intelligent_features is not None:
      # Delete legacy issue
      ir.async_delete_issue(hass, DOMAIN, REPAIR_UNKNOWN_INTELLIGENT_PROVIDER.format(intelligent_device.provider))
      if intelligent_features.is_default_features == True:
        ir.async_create_issue(
          hass,
          DOMAIN,
          REPAIR_UNKNOWN_INTELLIGENT_PROVIDER.format(intelligent_device.provider),
          is_fixable=False,
          severity=ir.IssueSeverity.WARNING,
          translation_key="unknown_intelligent_provider",
          translation_placeholders={ "account_id": account_id, "provider": intelligent_device.provider },
        )

      intelligent_repair_key = safe_repair_key("intelligent_manual_service_{}", account_id)
      if intelligent_features.planned_dispatches_supported and intelligent_manual_service_enabled == False:
        ir.async_create_issue(
          hass,
          DOMAIN,
          intelligent_repair_key,
          is_fixable=False,
          severity=ir.IssueSeverity.WARNING,
          translation_key="intelligent_manual_service",
          translation_placeholders={ "account_id": account_id, "polling_time": REFRESH_RATE_IN_MINUTES_INTELLIGENT },
        )
      else:
        ir.async_delete_issue(hass, DOMAIN, intelligent_repair_key)

        # Need to set initial data otherwise our rates won't update properly until an initial result has been requested
        if hass.data[DOMAIN][account_id][DATA_INTELLIGENT_DISPATCHES][intelligent_device.id] is None:
          hass.data[DOMAIN][account_id][DATA_INTELLIGENT_DISPATCHES][intelligent_device.id] = IntelligentDispatchesCoordinatorResult(
            now - timedelta(hours=1),
            1,
            IntelligentDispatches(None, [], []),
            IntelligentDispatchesHistory([]),
            0,
            now - timedelta(hours=1)
          )

    await async_setup_intelligent_dispatches_coordinator(
      hass,
      account_id,
      intelligent_device.id,
      should_mock_intelligent_data,
      intelligent_manual_service_enabled,
      intelligent_features.planned_dispatches_supported if intelligent_features is not None else True
    )

    await async_setup_intelligent_settings_coordinator(hass, account_id, intelligent_device.id, should_mock_intelligent_data)
    
    await async_setup_intelligent_devices_coordinator(hass, account_id, intelligent_devices, should_mock_intelligent_data)