from datetime import datetime
import pytest

from integration import (get_test_context)
from custom_components.edf_energy.api_client import EDFEnergyApiClient

period_from = datetime.strptime("2026-08-28T00:00:00Z", "%Y-%m-%dT%H:%M:%S%z")
period_to = datetime.strptime("2026-08-29T00:00:00Z", "%Y-%m-%dT%H:%M:%S%z")

@pytest.mark.asyncio
@pytest.mark.parametrize("product_code,tariff_code,expected_value,favour_direct_debit",
                         [("EDF_SIMPLY_FIXED_SEP2027", "G-1R-EDF_SIMPLY_FIXED_SEP2027-A", 28.7028, True),
                          ("EDF_SIMPLY_FIXED_SEP2027", "G-1R-EDF_SIMPLY_FIXED_SEP2027-A", 28.7028, False),
                          ("EDF_STANDARD_VARIABLE", "G-1R-EDF_STANDARD_VARIABLE-A", 28.7028, True),
                          ("EDF_STANDARD_VARIABLE", "G-1R-EDF_STANDARD_VARIABLE-A", 36.6975, False)])
async def test_when_get_gas_standing_charge_is_called_for_existent_tariff_then_rates_are_returned(product_code, tariff_code, expected_value, favour_direct_debit):
    # Arrange
    context = get_test_context()

    client = EDFEnergyApiClient(favour_direct_debit_rates=favour_direct_debit, api_key=context.refresh_token or "public")

    # Act
    result = await client.async_get_gas_standing_charge(product_code, tariff_code, period_from, period_to)

    # Assert
    assert result is not None
    assert "value_inc_vat" in result
    assert result["value_inc_vat"] == expected_value

@pytest.mark.asyncio
@pytest.mark.parametrize("product_code,tariff_code",[
    ("EDF_SIMPLY_FIXED_SEP2027", "G-1R-NOT-A-TARIFF-A"),
    ("EDF_SIMPLY_FIXED_SEP2027", "NOT-A-TARIFF"),
    ("NOT-A-PRODUCT", "G-1R-EDF_SIMPLY_FIXED_SEP2027-A")
])
async def test_when_get_gas_standing_charge_is_called_for_non_existent_tariff_then_none_is_returned(product_code, tariff_code):
    # Arrange
    context = get_test_context()

    client = EDFEnergyApiClient(api_key=context.refresh_token or "public")

    # Act
    result = await client.async_get_gas_standing_charge(product_code, tariff_code, period_from, period_to)

    # Assert
    assert result is None
