import pytest
import zoneinfo
from datetime import datetime, timedelta

from homeassistant.util.dt import set_default_time_zone

from custom_components.edf_energy.utils import get_off_peak_times
from custom_components.edf_energy.api_client import rates_to_thirty_minute_increments
from tests.unit import create_rate_data

GOELEC_TARIFF_CODE = "E-1R-EDF_EV_FIX_GOELEC_12M_HH-B"

def _build_off_peak_23_to_06_rates(period_from: datetime, period_to: datetime, tariff_code: str):
  """Build 30 minute rate slots for a tariff whose off-peak window runs 23:00 -> 06:00."""
  off_peak = 8.99997
  peak = 30.24714
  rates = []
  slot = period_from
  while slot < period_to:
    end = slot + timedelta(minutes=30)
    is_off_peak = slot.hour >= 23 or slot.hour < 6
    rates.append({
      "start": slot,
      "end": end,
      "value_inc_vat": off_peak if is_off_peak else peak,
      "tariff_code": tariff_code,
      "is_capped": False,
    })
    slot = end

  return rates

@pytest.mark.asyncio
async def test_when_rates_is_none_then_empty_list_returned():
  current = datetime.strptime("2023-10-14T00:00:01Z", "%Y-%m-%dT%H:%M:%S%z")
  
  # Act
  result = get_off_peak_times(current, None)

  # Assert
  assert result is not None
  assert len(result) == 0

@pytest.mark.asyncio
async def test_when_off_peak_rates_not_available_then_empty_list_returned():
  period_from = datetime.strptime("2023-10-14T00:00:00Z", "%Y-%m-%dT%H:%M:%S%z")
  period_to = datetime.strptime("2023-10-15T00:00:00Z", "%Y-%m-%dT%H:%M:%S%z")
  current = datetime.strptime("2023-10-14T00:00:01Z", "%Y-%m-%dT%H:%M:%S%z")
  rate_data = create_rate_data(period_from, period_to, [1, 2, 3, 4])
  
  # Act
  result = get_off_peak_times(current, rate_data)

  # Assert
  assert result is not None
  assert len(result) == 0

@pytest.mark.asyncio
async def test_when_off_peak_rates_in_past_then_not_included_in_list():
  period_from = datetime.strptime("2023-11-04T00:00:00Z", "%Y-%m-%dT%H:%M:%S%z")
  period_to = datetime.strptime("2023-11-07T00:00:00Z", "%Y-%m-%dT%H:%M:%S%z")
  current = datetime.strptime("2023-11-05T01:00:01Z", "%Y-%m-%dT%H:%M:%S%z")
  data = [
    {
			"value_exc_vat": 28.8068,
			"value_inc_vat": 30.24714,
			"valid_from": "2023-11-06T04:30:00Z",
			"valid_to": "2023-11-07T00:30:00Z"
		},
		{
			"value_exc_vat": 8.5714,
			"value_inc_vat": 8.99997,
			"valid_from": "2023-11-06T00:30:00Z",
			"valid_to": "2023-11-06T04:30:00Z"
		},
		{
			"value_exc_vat": 28.8068,
			"value_inc_vat": 30.24714,
			"valid_from": "2023-11-05T04:30:00Z",
			"valid_to": "2023-11-06T00:30:00Z"
		},
		{
			"value_exc_vat": 8.5714,
			"value_inc_vat": 8.99997,
			"valid_from": "2023-11-05T00:30:00Z",
			"valid_to": "2023-11-05T04:30:00Z"
		},
		{
			"value_exc_vat": 28.8068,
			"value_inc_vat": 30.24714,
			"valid_from": "2023-11-04T04:30:00Z",
			"valid_to": "2023-11-05T00:30:00Z"
		},
		{
			"value_exc_vat": 8.5714,
			"value_inc_vat": 8.99997,
			"valid_from": "2023-11-04T00:30:00Z",
			"valid_to": "2023-11-04T04:30:00Z"
		},
		{
			"value_exc_vat": 28.8068,
			"value_inc_vat": 30.24714,
			"valid_from": "2023-11-03T04:30:00Z",
			"valid_to": "2023-11-04T00:30:00Z"
		}
  ]
  rate_data = rates_to_thirty_minute_increments({ "results": data }, period_from, period_to, 'tariff')
  
  # Act
  result = get_off_peak_times(current, rate_data)

  # Assert
  assert result is not None
  assert len(result) == 2

  assert result[0].start == datetime.strptime("2023-11-05T00:30:00Z", "%Y-%m-%dT%H:%M:%S%z")
  assert result[0].end == datetime.strptime("2023-11-05T04:30:00Z", "%Y-%m-%dT%H:%M:%S%z")

  assert result[1].start == datetime.strptime("2023-11-06T00:30:00Z", "%Y-%m-%dT%H:%M:%S%z")
  assert result[1].end == datetime.strptime("2023-11-06T04:30:00Z", "%Y-%m-%dT%H:%M:%S%z")
  
@pytest.mark.asyncio
async def test_when_first_off_peak_rate_just_over_then_not_included_in_list():
  period_from = datetime.strptime("2023-11-04T00:00:00Z", "%Y-%m-%dT%H:%M:%S%z")
  period_to = datetime.strptime("2023-11-07T00:00:00Z", "%Y-%m-%dT%H:%M:%S%z")
  current = datetime.strptime("2023-11-05T04:30:01Z", "%Y-%m-%dT%H:%M:%S%z")
  data = [
    {
			"value_exc_vat": 28.8068,
			"value_inc_vat": 30.24714,
			"valid_from": "2023-11-06T04:30:00Z",
			"valid_to": "2023-11-07T00:30:00Z"
		},
		{
			"value_exc_vat": 8.5714,
			"value_inc_vat": 8.99997,
			"valid_from": "2023-11-06T00:30:00Z",
			"valid_to": "2023-11-06T04:30:00Z"
		},
		{
			"value_exc_vat": 28.8068,
			"value_inc_vat": 30.24714,
			"valid_from": "2023-11-05T04:30:00Z",
			"valid_to": "2023-11-06T00:30:00Z"
		},
		{
			"value_exc_vat": 8.5714,
			"value_inc_vat": 8.99997,
			"valid_from": "2023-11-05T00:30:00Z",
			"valid_to": "2023-11-05T04:30:00Z"
		},
		{
			"value_exc_vat": 28.8068,
			"value_inc_vat": 30.24714,
			"valid_from": "2023-11-04T04:30:00Z",
			"valid_to": "2023-11-05T00:30:00Z"
		},
		{
			"value_exc_vat": 8.5714,
			"value_inc_vat": 8.99997,
			"valid_from": "2023-11-04T00:30:00Z",
			"valid_to": "2023-11-04T04:30:00Z"
		},
		{
			"value_exc_vat": 28.8068,
			"value_inc_vat": 30.24714,
			"valid_from": "2023-11-03T04:30:00Z",
			"valid_to": "2023-11-04T00:30:00Z"
		}
  ]
  rate_data = rates_to_thirty_minute_increments({ "results": data }, period_from, period_to, 'tariff')
  
  # Act
  result = get_off_peak_times(current, rate_data)

  # Assert
  assert result is not None
  assert len(result) == 1

  assert result[0].start == datetime.strptime("2023-11-06T00:30:00Z", "%Y-%m-%dT%H:%M:%S%z")
  assert result[0].end == datetime.strptime("2023-11-06T04:30:00Z", "%Y-%m-%dT%H:%M:%S%z")
  
@pytest.mark.asyncio
async def test_when_intelligent_adjusted_rate_discovered_then_not_included_in_list():
  period_from = datetime.strptime("2023-11-04T00:00:00Z", "%Y-%m-%dT%H:%M:%S%z")
  period_to = datetime.strptime("2023-11-07T00:00:00Z", "%Y-%m-%dT%H:%M:%S%z")
  current = datetime.strptime("2023-11-05T01:00:01Z", "%Y-%m-%dT%H:%M:%S%z")
  data = [
    {
			"value_exc_vat": 28.8068,
			"value_inc_vat": 30.24714,
			"valid_from": "2023-11-06T04:30:00Z",
			"valid_to": "2023-11-07T00:30:00Z"
		},
		{
			"value_exc_vat": 8.5714,
			"value_inc_vat": 8.99997,
			"valid_from": "2023-11-06T00:30:00Z",
			"valid_to": "2023-11-06T04:30:00Z"
		},
		{
			"value_exc_vat": 28.8068,
			"value_inc_vat": 30.24714,
			"valid_from": "2023-11-05T04:30:00Z",
			"valid_to": "2023-11-06T00:30:00Z"
		},
    {
			"value_exc_vat": 8.5714,
			"value_inc_vat": 8.99997,
			"valid_from": "2023-11-05T00:30:00Z",
			"valid_to": "2023-11-05T04:30:00Z"
		},
		{
			"value_exc_vat": 28.8068,
			"value_inc_vat": 30.24714,
			"valid_from": "2023-11-04T04:30:00Z",
			"valid_to": "2023-11-05T00:30:00Z"
		},
		{
			"value_exc_vat": 8.5714,
			"value_inc_vat": 8.99997,
			"valid_from": "2023-11-04T00:30:00Z",
			"valid_to": "2023-11-04T04:30:00Z"
		},
		{
			"value_exc_vat": 28.8068,
			"value_inc_vat": 30.24714,
			"valid_from": "2023-11-03T04:30:00Z",
			"valid_to": "2023-11-04T00:30:00Z"
		}
  ]
  rate_data = rates_to_thirty_minute_increments({ "results": data }, period_from, period_to, 'tariff')
  
  for rate in rate_data:
    if rate["start"] == datetime.strptime("2023-11-05T02:00:00Z", "%Y-%m-%dT%H:%M:%S%z"):
      rate["is_intelligent_adjusted"] = True
  
  # Act
  result = get_off_peak_times(current, rate_data)

  # Assert
  assert result is not None
  assert len(result) == 3

  assert result[0].start == datetime.strptime("2023-11-05T00:30:00Z", "%Y-%m-%dT%H:%M:%S%z")
  assert result[0].end == datetime.strptime("2023-11-05T02:00:00Z", "%Y-%m-%dT%H:%M:%S%z")
  
  assert result[1].start == datetime.strptime("2023-11-05T02:30:00Z", "%Y-%m-%dT%H:%M:%S%z")
  assert result[1].end == datetime.strptime("2023-11-05T04:30:00Z", "%Y-%m-%dT%H:%M:%S%z")

  assert result[2].start == datetime.strptime("2023-11-06T00:30:00Z", "%Y-%m-%dT%H:%M:%S%z")
  assert result[2].end == datetime.strptime("2023-11-06T04:30:00Z", "%Y-%m-%dT%H:%M:%S%z")
  
@pytest.mark.asyncio
async def test_when_intelligent_adjusted_rate_discovered_and_specified_to_be_included_then_included_in_list():
  period_from = datetime.strptime("2023-11-04T00:00:00Z", "%Y-%m-%dT%H:%M:%S%z")
  period_to = datetime.strptime("2023-11-07T00:00:00Z", "%Y-%m-%dT%H:%M:%S%z")
  current = datetime.strptime("2023-11-05T01:00:01Z", "%Y-%m-%dT%H:%M:%S%z")
  include_intelligent_adjusted_rates = True
  data = [
    {
			"value_exc_vat": 28.8068,
			"value_inc_vat": 30.24714,
			"valid_from": "2023-11-06T04:30:00Z",
			"valid_to": "2023-11-07T00:30:00Z"
		},
		{
			"value_exc_vat": 8.5714,
			"value_inc_vat": 8.99997,
			"valid_from": "2023-11-06T00:30:00Z",
			"valid_to": "2023-11-06T04:30:00Z"
		},
		{
			"value_exc_vat": 28.8068,
			"value_inc_vat": 30.24714,
			"valid_from": "2023-11-05T04:30:00Z",
			"valid_to": "2023-11-06T00:30:00Z"
		},
    {
			"value_exc_vat": 8.5714,
			"value_inc_vat": 8.99997,
			"valid_from": "2023-11-05T00:30:00Z",
			"valid_to": "2023-11-05T04:30:00Z"
		},
		{
			"value_exc_vat": 28.8068,
			"value_inc_vat": 30.24714,
			"valid_from": "2023-11-04T04:30:00Z",
			"valid_to": "2023-11-05T00:30:00Z"
		},
		{
			"value_exc_vat": 8.5714,
			"value_inc_vat": 8.99997,
			"valid_from": "2023-11-04T00:30:00Z",
			"valid_to": "2023-11-04T04:30:00Z"
		},
		{
			"value_exc_vat": 28.8068,
			"value_inc_vat": 30.24714,
			"valid_from": "2023-11-03T04:30:00Z",
			"valid_to": "2023-11-04T00:30:00Z"
		}
  ]
  rate_data = rates_to_thirty_minute_increments({ "results": data }, period_from, period_to, 'tariff')
  
  for rate in rate_data:
    if rate["start"] == datetime.strptime("2023-11-05T02:00:00Z", "%Y-%m-%dT%H:%M:%S%z"):
      rate["is_intelligent_adjusted"] = True
  
  # Act
  result = get_off_peak_times(current, rate_data, include_intelligent_adjusted_rates)

  # Assert
  assert result is not None
  assert len(result) == 2

  assert result[0].start == datetime.strptime("2023-11-05T00:30:00Z", "%Y-%m-%dT%H:%M:%S%z")
  assert result[0].end == datetime.strptime("2023-11-05T04:30:00Z", "%Y-%m-%dT%H:%M:%S%z")

  assert result[1].start == datetime.strptime("2023-11-06T00:30:00Z", "%Y-%m-%dT%H:%M:%S%z")
  assert result[1].end == datetime.strptime("2023-11-06T04:30:00Z", "%Y-%m-%dT%H:%M:%S%z")
  
@pytest.mark.asyncio
async def test_when_intelligent_adjusted_rate_goes_beyond_rates_then_included_in_list():
  period_from = datetime.strptime("2023-11-04T00:00:00Z", "%Y-%m-%dT%H:%M:%S%z")
  period_to = datetime.strptime("2023-11-07T00:00:00Z", "%Y-%m-%dT%H:%M:%S%z")
  current = datetime.strptime("2023-11-05T08:00:01Z", "%Y-%m-%dT%H:%M:%S%z")
  include_intelligent_adjusted_rates = True
  data = [
		{
			"value_exc_vat": 28.8068,
			"value_inc_vat": 30.24714,
			"valid_from": "2023-11-05T04:30:00Z",
			"valid_to": "2023-11-06T00:30:00Z"
		},
    {
			"value_exc_vat": 8.5714,
			"value_inc_vat": 8.99997,
			"valid_from": "2023-11-05T00:30:00Z",
			"valid_to": "2023-11-05T04:30:00Z"
		},
		{
			"value_exc_vat": 28.8068,
			"value_inc_vat": 30.24714,
			"valid_from": "2023-11-04T04:30:00Z",
			"valid_to": "2023-11-05T00:30:00Z"
		},
		{
			"value_exc_vat": 8.5714,
			"value_inc_vat": 8.99997,
			"valid_from": "2023-11-04T00:30:00Z",
			"valid_to": "2023-11-04T04:30:00Z"
		},
		{
			"value_exc_vat": 28.8068,
			"value_inc_vat": 30.24714,
			"valid_from": "2023-11-03T04:30:00Z",
			"valid_to": "2023-11-04T00:30:00Z"
		}
  ]
  rate_data = rates_to_thirty_minute_increments({ "results": data }, period_from, period_to, 'tariff')
  
  for rate in rate_data:
    if rate["start"] >= datetime.strptime("2023-11-05T09:00:00Z", "%Y-%m-%dT%H:%M:%S%z") and rate["start"] <= datetime.strptime("2023-11-06T00:30:00Z", "%Y-%m-%dT%H:%M:%S%z"):
      rate["is_intelligent_adjusted"] = True
      rate["value_inc_vat"] = 8.99997
  
  # Act
  result = get_off_peak_times(current, rate_data, include_intelligent_adjusted_rates)

  # Assert
  assert result is not None
  assert len(result) == 1

  assert result[0].start == datetime.strptime("2023-11-05T09:00:00Z", "%Y-%m-%dT%H:%M:%S%z")
  assert result[0].end == datetime.strptime("2023-11-06T00:30:00Z", "%Y-%m-%dT%H:%M:%S%z")

@pytest.mark.asyncio
async def test_when_goelec_next_day_rates_truncated_then_uses_known_window_end():
  # Simulates the morning before the next day's rates have been published - the data ends at
  # midnight so the 23:00 -> 06:00 window would otherwise be truncated (issue #19).
  set_default_time_zone(zoneinfo.ZoneInfo("Europe/London"))
  try:
    period_from = datetime.strptime("2023-11-04T00:00:00Z", "%Y-%m-%dT%H:%M:%S%z")
    data_end = datetime.strptime("2023-11-06T00:00:00Z", "%Y-%m-%dT%H:%M:%S%z")
    current = datetime.strptime("2023-11-05T08:00:00Z", "%Y-%m-%dT%H:%M:%S%z")
    rate_data = _build_off_peak_23_to_06_rates(period_from, data_end, GOELEC_TARIFF_CODE)

    # Act
    result = get_off_peak_times(current, rate_data, True)

    # Assert - the truncated trailing window is extended to the known 06:00 end
    assert result is not None
    assert len(result) == 1
    assert result[0].start == datetime.strptime("2023-11-05T23:00:00Z", "%Y-%m-%dT%H:%M:%S%z")
    assert result[0].end == datetime.strptime("2023-11-06T06:00:00Z", "%Y-%m-%dT%H:%M:%S%z")
  finally:
    set_default_time_zone(zoneinfo.ZoneInfo("UTC"))

@pytest.mark.asyncio
async def test_when_goelec_full_day_available_then_api_end_used():
  # When the data actually reaches the end of the window the API value is used as-is, so the
  # known window fallback must not shift or override it.
  set_default_time_zone(zoneinfo.ZoneInfo("Europe/London"))
  try:
    period_from = datetime.strptime("2023-11-04T00:00:00Z", "%Y-%m-%dT%H:%M:%S%z")
    data_end = datetime.strptime("2023-11-06T06:00:00Z", "%Y-%m-%dT%H:%M:%S%z")
    current = datetime.strptime("2023-11-05T08:00:00Z", "%Y-%m-%dT%H:%M:%S%z")
    rate_data = _build_off_peak_23_to_06_rates(period_from, data_end, GOELEC_TARIFF_CODE)

    # Act
    result = get_off_peak_times(current, rate_data, True)

    # Assert
    assert result is not None
    assert len(result) == 1
    assert result[0].start == datetime.strptime("2023-11-05T23:00:00Z", "%Y-%m-%dT%H:%M:%S%z")
    assert result[0].end == datetime.strptime("2023-11-06T06:00:00Z", "%Y-%m-%dT%H:%M:%S%z")
  finally:
    set_default_time_zone(zoneinfo.ZoneInfo("UTC"))

@pytest.mark.asyncio
async def test_when_non_goelec_next_day_rates_truncated_then_end_not_extended():
  # Tariffs without a known off-peak window keep the existing behaviour - the trailing window
  # ends at the edge of the available data.
  set_default_time_zone(zoneinfo.ZoneInfo("Europe/London"))
  try:
    period_from = datetime.strptime("2023-11-04T00:00:00Z", "%Y-%m-%dT%H:%M:%S%z")
    data_end = datetime.strptime("2023-11-06T00:00:00Z", "%Y-%m-%dT%H:%M:%S%z")
    current = datetime.strptime("2023-11-05T08:00:00Z", "%Y-%m-%dT%H:%M:%S%z")
    rate_data = _build_off_peak_23_to_06_rates(period_from, data_end, "E-1R-EDF_STD_TEST-B")

    # Act
    result = get_off_peak_times(current, rate_data, True)

    # Assert
    assert result is not None
    assert len(result) == 1
    assert result[0].start == datetime.strptime("2023-11-05T23:00:00Z", "%Y-%m-%dT%H:%M:%S%z")
    assert result[0].end == datetime.strptime("2023-11-06T00:00:00Z", "%Y-%m-%dT%H:%M:%S%z")
  finally:
    set_default_time_zone(zoneinfo.ZoneInfo("UTC"))