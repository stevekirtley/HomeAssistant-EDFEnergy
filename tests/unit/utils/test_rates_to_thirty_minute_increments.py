from datetime import timedelta
import pytest

from homeassistant.util.dt import (as_utc, parse_datetime)
from custom_components.edf_energy.api_client import rates_to_thirty_minute_increments

# Based on E-1R-GO-22-07-05-D
@pytest.mark.asyncio
async def test_go_rates_bst():
  # Act
  period_from = as_utc(parse_datetime("2022-10-09T00:00+01:00"))
  period_to = as_utc(parse_datetime("2022-10-10T00:00+01:00"))
  tariff_code = "test_tariff"
  rates = [
    {
			"value_exc_vat": 40.274,
			"value_inc_vat": 42.2877,
			"valid_from": "2022-10-10T03:30:00Z",
			"valid_to": "2022-10-10T23:30:00Z"
		},
		{
			"value_exc_vat": 7.142,
			"value_inc_vat": 7.4991,
			"valid_from": "2022-10-09T23:30:00Z",
			"valid_to": "2022-10-10T03:30:00Z"
		},
		{
			"value_exc_vat": 40.274,
			"value_inc_vat": 42.2877,
			"valid_from": "2022-10-09T03:30:00Z",
			"valid_to": "2022-10-09T23:30:00Z"
		},
		{
			"value_exc_vat": 7.142,
			"value_inc_vat": 7.4991,
			"valid_from": "2022-10-08T23:30:00Z",
			"valid_to": "2022-10-09T03:30:00Z"
		},
		{
			"value_exc_vat": 40.274,
			"value_inc_vat": 42.2877,
			"valid_from": "2022-10-08T03:30:00Z",
			"valid_to": "2022-10-08T23:30:00Z"
		},
		{
			"value_exc_vat": 7.142,
			"value_inc_vat": 7.4991,
			"valid_from": "2022-10-07T23:30:00Z",
			"valid_to": "2022-10-08T03:30:00Z"
		},
		{
			"value_exc_vat": 40.274,
			"value_inc_vat": 42.2877,
			"valid_from": "2022-10-07T03:30:00Z",
			"valid_to": "2022-10-07T23:30:00Z"
		}
  ]
  
  result = rates_to_thirty_minute_increments(
    {
      "results": rates
    }, 
    period_from,
    period_to,
    tariff_code
  )

  # Assert
  assert result is not None
  assert len(result) == 48

  start_time = as_utc(parse_datetime("2022-10-09T00:00+01:00"))
  for index in range(48):
    end_time = start_time + timedelta(minutes=30)
    assert result[index]["start"] == start_time
    assert result[index]["end"] == end_time

    rates_index = 6
    if index < 1:
      rates_index = 4
    elif index < 9:
      rates_index = 5

    assert result[index]["value_inc_vat"] == rates[rates_index]["value_inc_vat"]

    assert result[index]["tariff_code"] == tariff_code

    start_time = end_time

  assert start_time == as_utc(parse_datetime("2022-10-10T00:00+01:00"))

def __full_day_rate(value_inc_vat: float, payment_method):
  return {
    "value_exc_vat": value_inc_vat,
    "value_inc_vat": value_inc_vat,
    "valid_from": "2026-06-04T23:00:00Z",
    "valid_to": "2026-06-05T23:00:00Z",
    "payment_method": payment_method,
  }

@pytest.mark.asyncio
async def test_direct_debit_only_tariff_still_returns_rates_when_not_favouring_direct_debit():
  # Regression for dynamic tariffs (e.g. EDF_FREEPHASE_DYNAMIC) that only publish
  # DIRECT_DEBIT rates - these must not be filtered away to nothing when the user
  # has not favoured direct debit rates.
  period_from = as_utc(parse_datetime("2026-06-05T00:00+01:00"))
  period_to = as_utc(parse_datetime("2026-06-06T00:00+01:00"))

  result = rates_to_thirty_minute_increments(
    { "results": [__full_day_rate(10.5, "DIRECT_DEBIT")] },
    period_from,
    period_to,
    "test_tariff",
    favour_direct_debit_rates=False,
  )

  assert len(result) == 48
  assert all(rate["value_inc_vat"] == 10.5 for rate in result)

@pytest.mark.asyncio
async def test_null_payment_method_rates_always_kept():
  # Tariffs whose rates carry no payment method (payment_method: null) are kept
  # regardless of the favour direct debit setting.
  period_from = as_utc(parse_datetime("2026-06-05T00:00+01:00"))
  period_to = as_utc(parse_datetime("2026-06-06T00:00+01:00"))

  result = rates_to_thirty_minute_increments(
    { "results": [__full_day_rate(7.0, None)] },
    period_from,
    period_to,
    "test_tariff",
    favour_direct_debit_rates=False,
  )

  assert len(result) == 48
  assert all(rate["value_inc_vat"] == 7.0 for rate in result)

@pytest.mark.asyncio
async def test_mixed_payment_methods_honour_the_favour_preference():
  # When both payment methods are present the favoured one is used.
  period_from = as_utc(parse_datetime("2026-06-05T00:00+01:00"))
  period_to = as_utc(parse_datetime("2026-06-06T00:00+01:00"))

  def both_methods():
    return [__full_day_rate(20.0, "DIRECT_DEBIT"), __full_day_rate(30.0, "NON_DIRECT_DEBIT")]

  favouring_direct_debit = rates_to_thirty_minute_increments(
    { "results": both_methods() }, period_from, period_to, "test_tariff", favour_direct_debit_rates=True
  )
  assert len(favouring_direct_debit) == 48
  assert all(rate["value_inc_vat"] == 20.0 for rate in favouring_direct_debit)

  not_favouring_direct_debit = rates_to_thirty_minute_increments(
    { "results": both_methods() }, period_from, period_to, "test_tariff", favour_direct_debit_rates=False
  )
  assert len(not_favouring_direct_debit) == 48
  assert all(rate["value_inc_vat"] == 30.0 for rate in not_favouring_direct_debit)