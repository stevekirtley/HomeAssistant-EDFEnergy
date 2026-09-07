import pytest
from datetime import datetime, timedelta

from unit import (create_consumption_data, create_rate_data)

from custom_components.edf_energy.statistics import build_cost_statistics

@pytest.mark.asyncio
async def test_when_target_rate_specified_then_statistics_restructed():
  # Arrange
  period_from = datetime.strptime("2022-02-28T00:00:00Z", "%Y-%m-%dT%H:%M:%S%z")
  period_to = datetime.strptime("2022-03-01T00:00:00Z", "%Y-%m-%dT%H:%M:%S%z")
  current = datetime.strptime("2022-02-28T00:00:01Z", "%Y-%m-%dT%H:%M:%S%z")
  consumptions = create_consumption_data(period_from, period_to, False, "start", "end")
  consumption_key = 'consumption'
  latest_total_sum = 3
  target_rate = 4
  rates = create_rate_data(period_from, period_to, [2, target_rate])

  # Act
  result = build_cost_statistics(
    current,
    consumptions,
    rates,
    consumption_key,
    latest_total_sum,
    target_rate=target_rate
  )

  # Assert
  assert result is not None

  expected_sum = latest_total_sum
  expected_state = 0

  for index in range(len(consumptions)):
    if index % 2 != 0:
      expected_sum += round((round(consumptions[index]["consumption"], 2) * round(rates[index]["value_inc_vat"], 2)) / 100, 6)
      expected_state += round((round(consumptions[index]["consumption"], 2) * round(rates[index]["value_inc_vat"], 2)) / 100, 6)
      
    if index % 2 == 1:
      expected_start = consumptions[index]["start"].replace(minute=0, second=0, microsecond=0)
      item = result[int(index / 2)]

      assert "start" in item
      assert item["start"] == expected_start

      assert "last_reset" in item
      assert item["last_reset"] == consumptions[0]["start"]

      assert "sum" in item
      assert item["sum"] == round(expected_sum, 2)

      assert "state" in item
      assert item["state"] == round(expected_state, 2)

@pytest.mark.asyncio
async def test_when_target_rate_not_specified_then_statistics_not_restricted():
  # Arrange
  period_from = datetime.strptime("2022-02-28T00:00:00Z", "%Y-%m-%dT%H:%M:%S%z")
  period_to = datetime.strptime("2022-03-01T00:00:00Z", "%Y-%m-%dT%H:%M:%S%z")
  current = datetime.strptime("2022-02-28T00:00:01Z", "%Y-%m-%dT%H:%M:%S%z")
  consumptions = create_consumption_data(period_from, period_to, False, "start", "end")
  rates = create_rate_data(period_from, period_to, [2, 4, 6])
  consumption_key = 'consumption'
  latest_total_sum = 3

  # Act
  result = build_cost_statistics(
    current,
    consumptions,
    rates,
    consumption_key,
    latest_total_sum
  )

  # Assert
  assert result is not None

  expected_sum = latest_total_sum
  expected_state = 0

  for index in range(len(consumptions)):
    item = result[int(index / 2)]
    expected_sum += round((round(consumptions[index]["consumption"], 2) * round(rates[index]["value_inc_vat"], 2)) / 100, 6)
    expected_state += round((round(consumptions[index]["consumption"], 2) * round(rates[index]["value_inc_vat"], 2)) / 100, 6)
    expected_start = consumptions[index]["start"].replace(minute=0, second=0, microsecond=0)

    if index % 2 == 1:
      assert "start" in item
      assert item["start"] == expected_start

      assert "last_reset" in item
      assert item["last_reset"] == consumptions[0]["start"]

      assert "sum" in item
      assert item["sum"] == round(expected_sum, 2)

      assert "state" in item
      assert item["state"] == round(expected_state, 2)
@pytest.mark.asyncio
async def test_when_half_hourly_costs_are_fractional_pennies_then_sum_is_not_inflated():
  """Half hourly costs must not be rounded to the penny before being summed.

  Rounding each of the 48 daily slots individually compounds the error across a
  day. Here every slot costs 2.642p, so the day should come to 126.816p (£1.27),
  but rounding each slot to £0.03 first gives £1.44 - about 13% too much.
  """
  # Arrange
  period_from = datetime.strptime("2022-02-28T00:00:00Z", "%Y-%m-%dT%H:%M:%S%z")
  rate = 26.4159
  consumption_per_slot = 0.1
  slots = 48

  consumptions = []
  rates = []
  for index in range(slots):
    start = period_from + timedelta(minutes=30 * index)
    end = start + timedelta(minutes=30)
    consumptions.append({"start": start, "end": end, "consumption": consumption_per_slot})
    rates.append({"start": start, "end": end, "value_inc_vat": rate})

  # Act
  result = build_cost_statistics(
    period_from,
    consumptions,
    rates,
    "consumption",
    0
  )

  # Assert
  # 0.10 kWh * 26.42p = 2.642p per slot, across 48 slots = 126.816p
  expected_total = round((consumption_per_slot * round(rate, 2) * slots) / 100, 2)
  assert expected_total == 1.27

  assert result[-1]["sum"] == expected_total
  assert result[-1]["state"] == expected_total
