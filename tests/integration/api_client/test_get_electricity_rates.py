"""Electricity unit rates from EDF's live pricing API.

The product is discovered rather than hard-coded; see tests/integration/__init__.py.

What matters here is the shape the client returns, not EDF's prices: a full day of
half-hourly periods, contiguous, correctly bounded, and capped when a cap is configured.
"""
from datetime import timedelta

import pytest

from integration import find_product, get_test_context, pricing_period
from custom_components.edf_energy.api_client import EDFEnergyApiClient

period_from, period_to = pricing_period()


async def async_assert_electricity_data(product, is_smart_meter, price_cap):
  # Arrange
  context = get_test_context()
  client = EDFEnergyApiClient(electricity_price_cap=price_cap,
                              api_key=context.refresh_token or "public")

  # Act
  data = await client.async_get_electricity_rates(
    product.code, product.electricity_tariff_code, is_smart_meter, period_from, period_to)

  # Assert
  assert data is not None, f"no rates for {product.code}"
  expected_periods = int((period_to - period_from).total_seconds() // 1800)
  assert len(data) == expected_periods, (
    f"{product.code}: expected {expected_periods} half hours, got {len(data)}")

  # Returned in contiguous thirty minute increments covering the whole period.
  expected_valid_from = period_from
  for item in data:
    expected_valid_to = expected_valid_from + timedelta(minutes=30)
    assert item["start"] == expected_valid_from, item
    assert item["end"] == expected_valid_to, item
    assert "value_inc_vat" in item
    assert item["value_inc_vat"] >= 0, item
    if price_cap is not None:
      assert item["value_inc_vat"] <= price_cap, item
    expected_valid_from = expected_valid_to

  assert expected_valid_from == period_to


@pytest.mark.asyncio
@pytest.mark.parametrize("is_variable", [True, False])
@pytest.mark.parametrize("price_cap", [None, 20])
async def test_when_get_electricity_rates_is_called_with_tariff_then_data_is_returned_in_thirty_minute_increments(
  is_variable, price_cap
):
  await async_assert_electricity_data(find_product(is_variable=is_variable), False, price_cap)


@pytest.mark.asyncio
async def test_when_get_electricity_rates_is_called_for_a_smart_meter_then_data_is_returned():
  await async_assert_electricity_data(find_product(is_variable=True), True, None)


@pytest.mark.asyncio
async def test_when_get_electricity_rates_is_called_for_non_existent_tariff_then_none_is_returned():
  context = get_test_context()
  product = find_product(is_variable=True)
  client = EDFEnergyApiClient(api_key=context.refresh_token or "public")

  data = await client.async_get_electricity_rates(
    product.code, "E-1R-NOT-A-TARIFF-A", False, period_from, period_to)

  assert data is None or len(data) == 0
