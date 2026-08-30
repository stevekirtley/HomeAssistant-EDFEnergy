from datetime import datetime
import pytest

from integration import (get_test_context)
from custom_components.edf_energy.api_client import EDFEnergyApiClient

period_from = datetime.strptime("2026-08-28T00:00:00Z", "%Y-%m-%dT%H:%M:%S%z")
period_to = datetime.strptime("2026-08-29T00:00:00Z", "%Y-%m-%dT%H:%M:%S%z")

@pytest.mark.asyncio
@pytest.mark.parametrize("product_code,tariff_code,expected_value_inc_vat,favour_direct_debit",[
    ("EDF_SIMPLY_FIXED_SEP2027", "E-1R-EDF_SIMPLY_FIXED_SEP2027-A", 53.94375, True),
    ("EDF_SIMPLY_FIXED_SEP2027", "E-1R-EDF_SIMPLY_FIXED_SEP2027-A", 53.94375, False),
    ("EDF_STANDARD_VARIABLE", "E-1R-EDF_STANDARD_VARIABLE-A", 53.94375, True),
    ("EDF_STANDARD_VARIABLE", "E-1R-EDF_STANDARD_VARIABLE-A", 62.7375, False),
])
async def test_when_get_electricity_standing_charge_is_called_for_existent_tariff_then_rates_are_returned(product_code, tariff_code, expected_value_inc_vat, favour_direct_debit):
    # Arrange
    context = get_test_context()

    client = EDFEnergyApiClient(favour_direct_debit_rates=favour_direct_debit, api_key=context.refresh_token or "public")

    # Act
    result = await client.async_get_electricity_standing_charge(product_code, tariff_code, period_from, period_to)

    # Assert
    assert result is not None
    assert "value_inc_vat" in result
    assert result["value_inc_vat"] == expected_value_inc_vat

@pytest.mark.asyncio
@pytest.mark.parametrize("product_code,tariff_code",[
    ("NOT-A-PRODUCT", "E-1R-NOT-A-TARIFF-A"),
    ("EDF_SIMPLY_FIXED_SEP2027", "NOT-A-TARIFF"),
    ("EDF_SIMPLY_FIXED_SEP2027", "E-1R-NOT-A-PRODUCT-A")
])
async def test_when_get_electricity_standing_charge_is_called_for_non_existent_tariff_then_none_is_returned(product_code, tariff_code):
    # Arrange
    context = get_test_context()

    client = EDFEnergyApiClient(api_key=context.refresh_token or "public")

    # Act
    result = await client.async_get_electricity_standing_charge(product_code, tariff_code, period_from, period_to)

    # Assert
    assert result is None
