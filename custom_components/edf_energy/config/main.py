import re
from ..const import (
  CONFIG_KIND,
  CONFIG_KIND_ACCOUNT,
  CONFIG_ACCOUNT_ID,
  CONFIG_MAIN_API_KEY,
  CONFIG_MAIN_ELECTRICITY_PRICE_CAP,
  CONFIG_MAIN_GAS_PRICE_CAP,
  CONFIG_MAIN_INTELLIGENT_MANUAL_DISPATCHES,
  CONFIG_MAIN_INTELLIGENT_RATE_MODE,
  CONFIG_MAIN_INTELLIGENT_SETTINGS,
  CONFIG_MAIN_OLD_ACCOUNT_ID,
  CONFIG_MAIN_OLD_API_KEY,
  CONFIG_MAIN_PRICE_CAP_SETTINGS,
)
from ..api_client import EDFEnergyApiClient, RequestException, ServerException

async def async_migrate_main_config(version: int, data: {}):
  new_data = {**data}

  if (version <= 1):
    new_data[CONFIG_KIND] = CONFIG_KIND_ACCOUNT

  if (version <= 2):
    new_data[CONFIG_KIND] = CONFIG_KIND_ACCOUNT

    if CONFIG_MAIN_OLD_API_KEY in new_data:
      new_data[CONFIG_MAIN_API_KEY] = new_data[CONFIG_MAIN_OLD_API_KEY]
      del new_data[CONFIG_MAIN_OLD_API_KEY]

    if CONFIG_MAIN_OLD_ACCOUNT_ID in new_data:
      new_data[CONFIG_ACCOUNT_ID] = new_data[CONFIG_MAIN_OLD_ACCOUNT_ID]
      del new_data[CONFIG_MAIN_OLD_ACCOUNT_ID]

  if (version <= 6):
    if CONFIG_MAIN_ELECTRICITY_PRICE_CAP in new_data or CONFIG_MAIN_GAS_PRICE_CAP in new_data:
      new_data[CONFIG_MAIN_PRICE_CAP_SETTINGS] = {}

      if CONFIG_MAIN_ELECTRICITY_PRICE_CAP in new_data:
        new_data[CONFIG_MAIN_PRICE_CAP_SETTINGS][CONFIG_MAIN_ELECTRICITY_PRICE_CAP] = new_data[CONFIG_MAIN_ELECTRICITY_PRICE_CAP]
        del new_data[CONFIG_MAIN_ELECTRICITY_PRICE_CAP]

      if CONFIG_MAIN_GAS_PRICE_CAP in new_data:
        new_data[CONFIG_MAIN_PRICE_CAP_SETTINGS][CONFIG_MAIN_GAS_PRICE_CAP] = new_data[CONFIG_MAIN_GAS_PRICE_CAP]
        del new_data[CONFIG_MAIN_GAS_PRICE_CAP]

    if CONFIG_MAIN_INTELLIGENT_MANUAL_DISPATCHES in new_data or CONFIG_MAIN_INTELLIGENT_RATE_MODE in new_data:
      new_data[CONFIG_MAIN_INTELLIGENT_SETTINGS] = {}

      if CONFIG_MAIN_INTELLIGENT_MANUAL_DISPATCHES in new_data:
        new_data[CONFIG_MAIN_INTELLIGENT_SETTINGS][CONFIG_MAIN_INTELLIGENT_MANUAL_DISPATCHES] = new_data[CONFIG_MAIN_INTELLIGENT_MANUAL_DISPATCHES]
        del new_data[CONFIG_MAIN_INTELLIGENT_MANUAL_DISPATCHES]

      if CONFIG_MAIN_INTELLIGENT_RATE_MODE in new_data:
        new_data[CONFIG_MAIN_INTELLIGENT_SETTINGS][CONFIG_MAIN_INTELLIGENT_RATE_MODE] = new_data[CONFIG_MAIN_INTELLIGENT_RATE_MODE]
        del new_data[CONFIG_MAIN_INTELLIGENT_RATE_MODE]

  return new_data

async def async_validate_main_config(data, account_ids = []):
  errors = {}

  if data[CONFIG_ACCOUNT_ID] in account_ids:
    errors[CONFIG_ACCOUNT_ID] = "duplicate_account"
    return errors

  if CONFIG_MAIN_API_KEY not in data:
    errors[CONFIG_MAIN_API_KEY] = "api_key_not_set"
    return errors

  client = EDFEnergyApiClient(data[CONFIG_MAIN_API_KEY])

  try:
    account_info = await client.async_get_account(data[CONFIG_ACCOUNT_ID])
  except RequestException:
    account_info = None
  except ServerException:
    errors[CONFIG_MAIN_API_KEY] = "server_error"

  if (CONFIG_MAIN_API_KEY not in errors and account_info is None):
    errors[CONFIG_MAIN_API_KEY] = "account_not_found"

  return errors
