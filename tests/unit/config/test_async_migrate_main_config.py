from custom_components.edf_energy.const import (
  CONFIG_ACCOUNT_ID,
  CONFIG_KIND,
  CONFIG_KIND_ACCOUNT,
  CONFIG_MAIN_API_KEY,
  CONFIG_MAIN_CALORIFIC_VALUE,
  CONFIG_MAIN_ELECTRICITY_PRICE_CAP,
  CONFIG_MAIN_GAS_PRICE_CAP,
  CONFIG_MAIN_INTELLIGENT_MANUAL_DISPATCHES,
  CONFIG_MAIN_INTELLIGENT_RATE_MODE,
  CONFIG_MAIN_INTELLIGENT_SETTINGS,
  CONFIG_MAIN_OLD_ACCOUNT_ID,
  CONFIG_MAIN_OLD_API_KEY,
  CONFIG_MAIN_PRICE_CAP_SETTINGS,
)
import pytest
from custom_components.edf_energy.config.main import async_migrate_main_config

data_v1 = {
  CONFIG_MAIN_OLD_API_KEY: "test-api-key",
  CONFIG_MAIN_OLD_ACCOUNT_ID: "A-123",
}

data_v2 = {
  CONFIG_MAIN_OLD_API_KEY: "test-api-key",
  CONFIG_MAIN_OLD_ACCOUNT_ID: "A-123",
}

data_v5 = {
  CONFIG_KIND: CONFIG_KIND_ACCOUNT,
  CONFIG_MAIN_API_KEY: "test-api-key",
  CONFIG_ACCOUNT_ID: "A-123",
  CONFIG_MAIN_CALORIFIC_VALUE: 40,
  CONFIG_MAIN_ELECTRICITY_PRICE_CAP: 38.5,
  CONFIG_MAIN_GAS_PRICE_CAP: 10.5,
  CONFIG_MAIN_INTELLIGENT_MANUAL_DISPATCHES: True,
  CONFIG_MAIN_INTELLIGENT_RATE_MODE: "intelligent_mode"
}

data_v5_no_intelligent_settings = {
  CONFIG_KIND: CONFIG_KIND_ACCOUNT,
  CONFIG_MAIN_API_KEY: "test-api-key",
  CONFIG_ACCOUNT_ID: "A-123",
  CONFIG_MAIN_CALORIFIC_VALUE: 40,
  CONFIG_MAIN_ELECTRICITY_PRICE_CAP: 38.5,
  CONFIG_MAIN_GAS_PRICE_CAP: 10.5,
}

data_v5_no_price_cap_settings = {
  CONFIG_KIND: CONFIG_KIND_ACCOUNT,
  CONFIG_MAIN_API_KEY: "test-api-key",
  CONFIG_ACCOUNT_ID: "A-123",
  CONFIG_MAIN_CALORIFIC_VALUE: 40,
  CONFIG_MAIN_INTELLIGENT_MANUAL_DISPATCHES: True,
  CONFIG_MAIN_INTELLIGENT_RATE_MODE: "intelligent_mode"
}

expected_data_v1 = {
  CONFIG_KIND: CONFIG_KIND_ACCOUNT,
  CONFIG_MAIN_API_KEY: "test-api-key",
  CONFIG_ACCOUNT_ID: "A-123",
}

expected_data_v5 = {
  CONFIG_KIND: CONFIG_KIND_ACCOUNT,
  CONFIG_MAIN_API_KEY: "test-api-key",
  CONFIG_ACCOUNT_ID: "A-123",
  CONFIG_MAIN_CALORIFIC_VALUE: 40,
  CONFIG_MAIN_PRICE_CAP_SETTINGS: {
    CONFIG_MAIN_ELECTRICITY_PRICE_CAP: 38.5,
    CONFIG_MAIN_GAS_PRICE_CAP: 10.5,
  },
  CONFIG_MAIN_INTELLIGENT_SETTINGS: {
    CONFIG_MAIN_INTELLIGENT_MANUAL_DISPATCHES: True,
    CONFIG_MAIN_INTELLIGENT_RATE_MODE: "intelligent_mode"
  }
}

expected_data_v5_no_intelligent_settings = {
  CONFIG_KIND: CONFIG_KIND_ACCOUNT,
  CONFIG_MAIN_API_KEY: "test-api-key",
  CONFIG_ACCOUNT_ID: "A-123",
  CONFIG_MAIN_CALORIFIC_VALUE: 40,
  CONFIG_MAIN_PRICE_CAP_SETTINGS: {
    CONFIG_MAIN_ELECTRICITY_PRICE_CAP: 38.5,
    CONFIG_MAIN_GAS_PRICE_CAP: 10.5,
  },
}

expected_data_v5_no_price_cap_settings = {
  CONFIG_KIND: CONFIG_KIND_ACCOUNT,
  CONFIG_MAIN_API_KEY: "test-api-key",
  CONFIG_ACCOUNT_ID: "A-123",
  CONFIG_MAIN_CALORIFIC_VALUE: 40,
  CONFIG_MAIN_INTELLIGENT_SETTINGS: {
    CONFIG_MAIN_INTELLIGENT_MANUAL_DISPATCHES: True,
    CONFIG_MAIN_INTELLIGENT_RATE_MODE: "intelligent_mode"
  }
}

@pytest.mark.asyncio
@pytest.mark.parametrize("version,data,expected_data",[
  (1, data_v1, expected_data_v1),
  (2, data_v2, expected_data_v1),
  (5, data_v5, expected_data_v5),
  (5, data_v5_no_intelligent_settings, expected_data_v5_no_intelligent_settings),
  (5, data_v5_no_price_cap_settings, expected_data_v5_no_price_cap_settings),
])
async def test_when_data_is_provided_then_migrated_correctly(version, data, expected_data):
  # Act
  updated_data = await async_migrate_main_config(version, data)

  # Assert
  assert updated_data == expected_data
