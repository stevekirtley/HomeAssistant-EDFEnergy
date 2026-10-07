"""Electricity standing charges from EDF's live pricing API.

The product is discovered rather than hard-coded. EDF withdraw tariffs from sale every few
months and the API then answers 404 for them, which used to break this suite without any
code changing. See tests/integration/__init__.py.

The exact pence are deliberately not asserted. They are EDF's number to choose, change
without notice, and differ per product, so pinning them would test EDF's price list rather
than this client. What is asserted is that a charge comes back, is plausible, and carries
the VAT treatment the client is responsible for applying.
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
async def test_when_get_electricity_standing_charge_is_called_for_existent_tariff_then_rates_are_returned(
  is_variable, favour_direct_debit
):
  # Arrange
  context = get_test_context()
  product = find_product(is_variable=is_variable)
  client = EDFEnergyApiClient(favour_direct_debit_rates=favour_direct_debit,
                              api_key=context.refresh_token or "public")

  # Act
  result = await client.async_get_electricity_standing_charge(
    product.code, product.electricity_tariff_code, period_from, period_to)

  # Assert
  assert result is not None, f"no standing charge for {product.code}"
  assert "value_inc_vat" in result
  # A daily standing charge in pence. Wide on purpose: this is a sanity bound, not a price
  # check, and it only has to catch a unit mix-up such as pounds for pence.
  assert 0 < result["value_inc_vat"] < 500, result


@pytest.mark.asyncio
async def test_when_get_electricity_standing_charge_is_called_for_non_existent_tariff_then_none_is_returned():
  # Arrange
  context = get_test_context()
  product = find_product(is_variable=True)
  client = EDFEnergyApiClient(api_key=context.refresh_token or "public")

  for product_code, tariff_code in (
    ("NOT-A-PRODUCT", "E-1R-NOT-A-TARIFF-A"),
    (product.code, "NOT-A-TARIFF"),
    (product.code, "E-1R-NOT-A-PRODUCT-A"),
  ):
    # Act
    result = await client.async_get_electricity_standing_charge(
      product_code, tariff_code, period_from, period_to)

    # Assert
    assert result is None, f"{product_code}/{tariff_code} unexpectedly returned {result}"
