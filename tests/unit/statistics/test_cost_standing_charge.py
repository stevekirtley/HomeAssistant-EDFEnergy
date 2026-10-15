import pytest
from datetime import datetime

from unit import (create_consumption_data, create_rate_data)

from custom_components.edf_energy.statistics import build_cost_statistics
from custom_components.edf_energy.statistics.cost import (
  get_electricity_cost_including_standing_charge_statistic_name,
  get_electricity_cost_including_standing_charge_statistic_unique_id,
  get_electricity_cost_statistic_unique_id,
  get_gas_cost_including_standing_charge_statistic_name,
  get_gas_cost_including_standing_charge_statistic_unique_id,
)

period_from = datetime.strptime("2022-02-28T00:00:00Z", "%Y-%m-%dT%H:%M:%S%z")
period_to = datetime.strptime("2022-03-01T00:00:00Z", "%Y-%m-%dT%H:%M:%S%z")
current = datetime.strptime("2022-02-28T00:00:01Z", "%Y-%m-%dT%H:%M:%S%z")

def build(standing_charge_in_pence = 0, target_rate = None, latest_total_sum = 0):
  consumptions = create_consumption_data(period_from, period_to, False, "start", "end")
  rates = create_rate_data(period_from, period_to, [2, 4])
  return build_cost_statistics(
    current,
    consumptions,
    rates,
    'consumption',
    latest_total_sum,
    target_rate=target_rate,
    standing_charge_in_pence=standing_charge_in_pence
  )

@pytest.mark.asyncio
async def test_when_standing_charge_not_supplied_then_statistics_unchanged():
  # Arrange/Act
  without = build()
  explicit_zero = build(standing_charge_in_pence=0)

  # Assert
  assert without == explicit_zero

@pytest.mark.asyncio
async def test_when_standing_charge_supplied_then_added_to_every_statistic_once():
  # Arrange
  standing_charge_in_pence = 47.85
  expected = round(standing_charge_in_pence / 100, 6)

  # Act
  without = build()
  with_charge = build(standing_charge_in_pence=standing_charge_in_pence)

  # Assert
  assert len(with_charge) == len(without)

  # Every hour of the day carries the charge, because the running total it was seeded into
  # never resets within the day - but it is only ever counted the once.
  for index in range(len(with_charge)):
    assert with_charge[index]["sum"] == round(without[index]["sum"] + expected, 2)
    assert with_charge[index]["state"] == round(without[index]["state"] + expected, 2)

@pytest.mark.asyncio
async def test_when_standing_charge_supplied_then_previous_sum_still_carried():
  # Arrange
  standing_charge_in_pence = 47.85
  latest_total_sum = 12.34

  # Act
  result = build(standing_charge_in_pence=standing_charge_in_pence, latest_total_sum=latest_total_sum)
  from_zero = build(standing_charge_in_pence=standing_charge_in_pence, latest_total_sum=0)

  # Assert
  assert result[0]["sum"] == round(from_zero[0]["sum"] + latest_total_sum, 2)
  # The state is the day's own total, so the sum carried over must not reach it.
  assert result[0]["state"] == from_zero[0]["state"]

@pytest.mark.asyncio
async def test_when_target_rate_specified_then_standing_charge_not_applied():
  """A daily charge belongs to neither band, so the peak/off peak breakdowns leave it out."""
  # Act
  without = build(target_rate=4)
  with_charge = build(standing_charge_in_pence=47.85, target_rate=4)

  # Assert
  assert with_charge == without

@pytest.mark.asyncio
async def test_including_standing_charge_ids_sit_alongside_the_originals():
  # Act/Assert
  assert (get_electricity_cost_including_standing_charge_statistic_unique_id("123", "456", False)
          == "electricity_123_456_previous_accumulative_cost_includingsc")
  assert (get_electricity_cost_including_standing_charge_statistic_unique_id("123", "456", True)
          == "electricity_123_456_export_previous_accumulative_cost_includingsc")
  assert (get_gas_cost_including_standing_charge_statistic_unique_id("123", "456")
          == "gas_123_456_previous_accumulative_cost_includingsc")

  # The original must keep its id exactly, or everybody's history detaches from it.
  assert get_electricity_cost_statistic_unique_id("123", "456", False) == "electricity_123_456_previous_accumulative_cost"

@pytest.mark.asyncio
async def test_including_standing_charge_names_say_what_they_are():
  # Act/Assert
  assert (get_electricity_cost_including_standing_charge_statistic_name("123", "456", False)
          == "Electricity 123 456 Previous Accumulative Cost Including Standing Charge")
  assert (get_gas_cost_including_standing_charge_statistic_name("123", "456")
          == "Gas 123 456 Previous Accumulative Cost Including Standing Charge")
