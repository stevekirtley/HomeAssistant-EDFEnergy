import pytest
import mock

from custom_components.edf_energy.api_client import EDFEnergyApiClient, RequestException, ServerException
from custom_components.edf_energy.config.main import async_validate_main_config
from custom_components.edf_energy.const import (
  CONFIG_ACCOUNT_ID,
  CONFIG_MAIN_API_KEY,
  CONFIG_MAIN_CALORIFIC_VALUE,
  CONFIG_MAIN_PRICE_CAP_SETTINGS,
  CONFIG_MAIN_ELECTRICITY_PRICE_CAP,
  CONFIG_MAIN_GAS_PRICE_CAP
)
from . import assert_errors_not_present

mpan = "selected-mpan"

config_keys = [
  CONFIG_MAIN_API_KEY,
  CONFIG_MAIN_CALORIFIC_VALUE,
  CONFIG_MAIN_ELECTRICITY_PRICE_CAP,
  CONFIG_MAIN_GAS_PRICE_CAP,
]

def get_account_info():
  return {
    "electricity_meter_points": [
      {
        "mpan": mpan,
        "agreements": [
          {
            "start": "2023-08-01T00:00:00+01:00",
            "end": "2023-09-01T00:00:00+01:00",
            "tariff_code": "E-1R-SUPER-GREEN-24M-21-07-30-C",
            "product_code": "SUPER-GREEN-24M-21-07-30"
          }
        ]
      }
    ]
  }

@pytest.mark.asyncio
async def test_when_data_is_valid_and_minimal_then_no_errors_returned():
  # Arrange
  data = {
    CONFIG_MAIN_API_KEY: "test-api-key",
    CONFIG_ACCOUNT_ID: "A-123",
    CONFIG_MAIN_CALORIFIC_VALUE: 40
  }

  account_info = get_account_info()
  async def async_mocked_get_account(*args, **kwargs):
    return account_info

  # Act
  with mock.patch.multiple(EDFEnergyApiClient, async_get_account=async_mocked_get_account):
    errors = await async_validate_main_config(data)

    # Assert
    assert_errors_not_present(errors, config_keys)

@pytest.mark.asyncio
async def test_when_data_is_valid_then_no_errors_returned():
  # Arrange
  data = {
    CONFIG_MAIN_API_KEY: "test-api-key",
    CONFIG_ACCOUNT_ID: "A-123",
    CONFIG_MAIN_CALORIFIC_VALUE: 40,
    CONFIG_MAIN_PRICE_CAP_SETTINGS: {
      CONFIG_MAIN_ELECTRICITY_PRICE_CAP: 38.5,
      CONFIG_MAIN_GAS_PRICE_CAP: 10.5,
    }
  }

  account_info = get_account_info()
  async def async_mocked_get_account(*args, **kwargs):
    return account_info

  # Act
  with mock.patch.multiple(EDFEnergyApiClient, async_get_account=async_mocked_get_account):
    errors = await async_validate_main_config(data)

    # Assert
    assert_errors_not_present(errors, config_keys)

@pytest.mark.asyncio
async def test_when_account_info_not_found_then_errors_returned():
  # Arrange
  data = {
    CONFIG_MAIN_API_KEY: "test-api-key",
    CONFIG_ACCOUNT_ID: "A-123",
    CONFIG_MAIN_CALORIFIC_VALUE: 40,
  }

  async def async_mocked_get_account(*args, **kwargs):
    return None

  # Act
  with mock.patch.multiple(EDFEnergyApiClient, async_get_account=async_mocked_get_account):
    errors = await async_validate_main_config(data)

    # Assert
    assert CONFIG_MAIN_API_KEY in errors
    assert errors[CONFIG_MAIN_API_KEY] == "account_not_found"

    assert_errors_not_present(errors, config_keys, CONFIG_MAIN_API_KEY)

@pytest.mark.asyncio
async def test_when_account_info_raises_server_error_then_errors_returned():
  # Arrange
  data = {
    CONFIG_MAIN_API_KEY: "test-api-key",
    CONFIG_ACCOUNT_ID: "A-123",
    CONFIG_MAIN_CALORIFIC_VALUE: 40,
  }

  async def async_mocked_get_account(*args, **kwargs):
    raise ServerException()

  # Act
  with mock.patch.multiple(EDFEnergyApiClient, async_get_account=async_mocked_get_account):
    errors = await async_validate_main_config(data)

    # Assert
    assert CONFIG_MAIN_API_KEY in errors
    assert errors[CONFIG_MAIN_API_KEY] == "server_error"

    assert_errors_not_present(errors, config_keys, CONFIG_MAIN_API_KEY)

@pytest.mark.asyncio
async def test_when_account_info_raises_request_error_then_errors_returned():
  # Arrange
  data = {
    CONFIG_MAIN_API_KEY: "test-api-key",
    CONFIG_ACCOUNT_ID: "A-123",
    CONFIG_MAIN_CALORIFIC_VALUE: 40,
  }

  async def async_mocked_get_account(*args, **kwargs):
    raise RequestException("blah", [])

  # Act
  with mock.patch.multiple(EDFEnergyApiClient, async_get_account=async_mocked_get_account):
    errors = await async_validate_main_config(data)

    # Assert
    assert CONFIG_MAIN_API_KEY in errors
    assert errors[CONFIG_MAIN_API_KEY] == "account_not_found"

    assert_errors_not_present(errors, config_keys, CONFIG_MAIN_API_KEY)

@pytest.mark.asyncio
async def test_when_account_has_been_setup_already_then_errors_returned():
  # Arrange
  data = {
    CONFIG_MAIN_API_KEY: "test-api-key",
    CONFIG_ACCOUNT_ID: "A-123",
    CONFIG_MAIN_CALORIFIC_VALUE: 40,
  }

  account_info = get_account_info()
  async def async_mocked_get_account(*args, **kwargs):
    return account_info

  # Act
  with mock.patch.multiple(EDFEnergyApiClient, async_get_account=async_mocked_get_account):
    errors = await async_validate_main_config(data, [data[CONFIG_ACCOUNT_ID]])

    # Assert
    assert CONFIG_ACCOUNT_ID in errors
    assert errors[CONFIG_ACCOUNT_ID] == "duplicate_account"

    assert_errors_not_present(errors, config_keys, CONFIG_ACCOUNT_ID)
