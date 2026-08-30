from datetime import datetime, timedelta
import pytest

from integration import (get_test_context)
from custom_components.edf_energy.api_client import EDFEnergyApiClient

default_period_from = datetime.strptime("2026-08-28T00:00:00Z", "%Y-%m-%dT%H:%M:%S%z")
default_period_to = datetime.strptime("2026-08-29T00:00:00Z", "%Y-%m-%dT%H:%M:%S%z")

@pytest.mark.asyncio
@pytest.mark.parametrize("product_code,tariff_code,price_cap,period_from,period_to",[
    ("EDF_SIMPLY_FIXED_SEP2027", "G-1R-EDF_SIMPLY_FIXED_SEP2027-A", None, datetime.strptime("2026-08-28T00:00:00Z", "%Y-%m-%dT%H:%M:%S%z"), datetime.strptime("2026-08-29T00:00:00Z", "%Y-%m-%dT%H:%M:%S%z")),
    ("EDF_SIMPLY_FIXED_SEP2027", "G-1R-EDF_SIMPLY_FIXED_SEP2027-A", 2, datetime.strptime("2026-08-28T00:00:00Z", "%Y-%m-%dT%H:%M:%S%z"), datetime.strptime("2026-08-29T00:00:00Z", "%Y-%m-%dT%H:%M:%S%z")),
    ("EDF_STANDARD_VARIABLE", "G-1R-EDF_STANDARD_VARIABLE-A", None, datetime.strptime("2026-08-28T00:00:00Z", "%Y-%m-%dT%H:%M:%S%z"), datetime.strptime("2026-08-29T00:00:00Z", "%Y-%m-%dT%H:%M:%S%z")),
])
async def test_when_get_gas_rates_is_called_for_existent_tariff_then_rates_are_returned(product_code, tariff_code, price_cap, period_from, period_to):
    # Arrange
    context = get_test_context()

    client = EDFEnergyApiClient(gas_price_cap=price_cap, api_key=context.refresh_token or "public")

    # Act
    data = await client.async_get_gas_rates(product_code, tariff_code, period_from, period_to)

    # Assert
    assert data is not None
    assert len(data) == 48

    # Make sure our data is returned in 30 minute increments
    expected_valid_from = period_from
    for item in data:
        expected_valid_to = expected_valid_from + timedelta(minutes=30)

        assert "start" in item
        assert item["start"] == expected_valid_from
        assert "end" in item
        assert item["end"] == expected_valid_to

        assert "value_inc_vat" in item
        if price_cap is not None:
            assert item["value_inc_vat"] <= price_cap

        expected_valid_from = expected_valid_to

@pytest.mark.asyncio
@pytest.mark.parametrize("product_code,tariff_code",[
    ("NOT-A-PRODUCT", "G-1R-NOT-A-PRODUCT-A"),
    ("EDF_SIMPLY_FIXED_SEP2027", "NOT-A-TARIFF"),
    ("NOT-A-PRODUCT", "G-1R-EDF_SIMPLY_FIXED_SEP2027-A")
])
async def test_when_get_gas_rates_is_called_for_non_existent_tariff_then_none_is_returned(product_code, tariff_code):
    # Arrange
    context = get_test_context()

    client = EDFEnergyApiClient(api_key=context.refresh_token or "public")

    # Act
    data = await client.async_get_gas_rates(product_code, tariff_code, default_period_from, default_period_to)

    # Assert
    assert data is None
