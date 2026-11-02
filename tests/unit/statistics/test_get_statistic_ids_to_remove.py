import pytest
from datetime import datetime

from custom_components.edfenergy_uk.const import DOMAIN, STATISTICS_SOURCE
from custom_components.edfenergy_uk.statistics import get_statistic_ids_to_remove


def both_domains(*suffixes):
  """Each id as it is written, and again under this domain's own prefix.

  The written prefix never changes - the recorder cannot rename an external statistic - but
  21.0.0 wrote a day of them under this domain before that was understood, and the purge is
  the only thing that would ever clear those.
  """
  return ([f"{STATISTICS_SOURCE}:{s}" for s in suffixes]
          + [f"{DOMAIN}:{s}" for s in suffixes])

def get_account_info():
  return {
    "electricity_meter_points": [
      {
        "mpan": 'elec-mpan',
        "agreements": [
          {
            "start": "2023-08-01T00:00:00+01:00",
            "end": "2023-08-14T00:00:00+01:00",
            "tariff_code": "E-1R-SUPER-GREEN-24M-21-07-30-C",
            "product_code": "SUPER-GREEN-24M-21-07-30"
          }
        ],
        "meters": [
          {
            "serial_number": 'elec-sn',
            "is_export": True,
          }
        ]
      }
    ],
    "gas_meter_points": [
      {
        "mprn": 'gas-mprn',
        "agreements": [
          {
            "start": "2023-08-13T00:00:00+01:00",
            "end": "2023-09-01T00:00:00+01:00",
            "tariff_code": "G-1R-SUPER-GREEN-24M-21-07-30-C",
            "product_code": "SUPER-GREEN-24M-21-07-30"
          }
        ],
        "meters": [
          {
            "serial_number": 'gas-sn'
          }
        ]
      }
    ]
  }

def test_when_account_info_is_none_then_empty_list_returned():
  # Arrange
  now = datetime.strptime("2023-08-13T00:00:00+01:00", "%Y-%m-%dT%H:%M:%S%z")
  account_info = None

  # Act
  result = get_statistic_ids_to_remove(now, account_info)

  # Assert
  assert len(result) == 0

def test_when_all_meters_have_valid_tariff_then_empty_list_returned():
  # Arrange
  now = datetime.strptime("2023-08-13T00:00:00+01:00", "%Y-%m-%dT%H:%M:%S%z")
  account_info = get_account_info()

  # Act
  result = get_statistic_ids_to_remove(now, account_info)

  # Assert
  assert len(result) == 0

def test_when_electricity_meter_have_valid_tariff_then_electricity_meters_returned():
  # Arrange
  now = datetime.strptime("2023-08-15T00:00:00+01:00", "%Y-%m-%dT%H:%M:%S%z")
  account_info = get_account_info()

  # Act
  result = get_statistic_ids_to_remove(now, account_info)

  # Assert
  assert result == both_domains("electricity_elec-sn_elec-mpan_export_previous_accumulative_consumption", "electricity_elec-sn_elec-mpan_export_previous_accumulative_cost", "electricity_elec-sn_elec-mpan_previous_accumulative_cost")

def test_when_gas_meter_have_valid_tariff_then_gas_meters_returned():
  # Arrange
  now = datetime.strptime("2023-08-12T00:00:00+01:00", "%Y-%m-%dT%H:%M:%S%z")
  account_info = get_account_info()

  # Act
  result = get_statistic_ids_to_remove(now, account_info)

  # Assert
  assert result == both_domains("gas_gas-sn_gas-mprn_previous_accumulative_consumption", "gas_gas-sn_gas-mprn_previous_accumulative_cost")

def test_when_electricity_and_gas_meter_have_valid_tariff_then_electricity_and_gas_meters_returned():
  # Arrange
  now = datetime.strptime("2023-09-02T00:00:00+01:00", "%Y-%m-%dT%H:%M:%S%z")
  account_info = get_account_info()

  # Act
  result = get_statistic_ids_to_remove(now, account_info)

  # Assert
  assert result == both_domains("electricity_elec-sn_elec-mpan_export_previous_accumulative_consumption", "electricity_elec-sn_elec-mpan_export_previous_accumulative_cost", "electricity_elec-sn_elec-mpan_previous_accumulative_cost", "gas_gas-sn_gas-mprn_previous_accumulative_consumption", "gas_gas-sn_gas-mprn_previous_accumulative_cost")
