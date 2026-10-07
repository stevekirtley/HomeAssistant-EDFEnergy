"""Gas unit rates from EDF's live pricing API.

The product is discovered rather than hard-coded; see tests/integration/__init__.py.
"""
import pytest

from integration import find_product, get_test_context, pricing_period
from custom_components.edf_energy.api_client import EDFEnergyApiClient

period_from, period_to = pricing_period()


@pytest.mark.asyncio
@pytest.mark.parametrize("is_variable", [True, False])
@pytest.mark.parametrize("price_cap", [None, 2])
async def test_when_get_gas_rates_is_called_for_existent_tariff_then_rates_are_returned(
  is_variable, price_cap
):
  # Arrange
  context = get_test_context()
  product = find_product(is_variable=is_variable, needs_gas=True)
  client = EDFEnergyApiClient(gas_price_cap=price_cap, api_key=context.refresh_token or "public")

  # Act
  data = await client.async_get_gas_rates(
    product.code, product.gas_tariff_code, period_from, period_to)

  # Assert
  assert data is not None, f"no gas rates for {product.code}"
  assert len(data) > 0
  for item in data:
    assert "start" in item and "end" in item and "value_inc_vat" in item
    assert item["end"] > item["start"]
    assert item["value_inc_vat"] >= 0
    if price_cap is not None:
      # The cap is the point of the setting: nothing may be published above it.
      assert item["value_inc_vat"] <= price_cap, item


@pytest.mark.asyncio
async def test_when_get_gas_rates_is_called_for_non_existent_tariff_then_none_is_returned():
  context = get_test_context()
  product = find_product(is_variable=True, needs_gas=True)
  client = EDFEnergyApiClient(api_key=context.refresh_token or "public")

  data = await client.async_get_gas_rates(
    product.code, "G-1R-NOT-A-TARIFF-A", period_from, period_to)

  assert data is None
