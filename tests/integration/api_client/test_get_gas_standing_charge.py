"""Gas standing charges from EDF's live pricing API.

The product is discovered rather than hard-coded; see tests/integration/__init__.py for
why. Exact pence are EDF's to change, so what is checked is that a charge comes back, is
plausible, and carries the VAT the client is responsible for applying.
"""
# These endpoints return only an inclusive-of-VAT figure - {start, end, value_inc_vat,
# tariff_code} - so there is no VAT relationship to assert here. An earlier version of
# this file checked one against a value_exc_vat that does not exist.

import pytest

from integration import find_product, get_test_context, pricing_period
from custom_components.edf_energy.api_client import EDFEnergyApiClient

period_from, period_to = pricing_period()


@pytest.mark.asyncio
@pytest.mark.parametrize("is_variable", [True, False])
@pytest.mark.parametrize("favour_direct_debit", [True, False])
async def test_when_get_gas_standing_charge_is_called_for_existent_tariff_then_rates_are_returned(
  is_variable, favour_direct_debit
):
  # Arrange
  context = get_test_context()
  product = find_product(is_variable=is_variable, needs_gas=True)
  client = EDFEnergyApiClient(favour_direct_debit_rates=favour_direct_debit,
                              api_key=context.refresh_token or "public")

  # Act
  result = await client.async_get_gas_standing_charge(
    product.code, product.gas_tariff_code, period_from, period_to)

  # Assert
  assert result is not None, f"no gas standing charge for {product.code}"
  assert "value_inc_vat" in result
  assert 0 < result["value_inc_vat"] < 500, result


@pytest.mark.asyncio
async def test_when_get_gas_standing_charge_is_called_for_non_existent_tariff_then_none_is_returned():
  context = get_test_context()
  product = find_product(is_variable=True, needs_gas=True)
  client = EDFEnergyApiClient(api_key=context.refresh_token or "public")

  for product_code, tariff_code in (
    ("NOT-A-PRODUCT", "G-1R-NOT-A-TARIFF-A"),
    (product.code, "NOT-A-TARIFF"),
    (product.code, "G-1R-NOT-A-PRODUCT-A"),
  ):
    result = await client.async_get_gas_standing_charge(
      product_code, tariff_code, period_from, period_to)

    assert result is None, f"{product_code}/{tariff_code} unexpectedly returned {result}"
