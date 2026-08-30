from datetime import datetime, timedelta
import pytest

from integration import (get_test_context)
from custom_components.edf_energy.api_client import EDFEnergyApiClient

default_period_from = datetime.strptime("2026-08-28T00:00:00Z", "%Y-%m-%dT%H:%M:%S%z")
default_period_to = datetime.strptime("2026-08-29T00:00:00Z", "%Y-%m-%dT%H:%M:%S%z")

async def async_assert_electricity_data(product_code, tariff_code, is_smart_meter, price_cap, period_from = default_period_from, period_to = default_period_to, expected_rates = None):
    # Arrange
    context = get_test_context()

    client = EDFEnergyApiClient(electricity_price_cap=price_cap, api_key=context.refresh_token or "public")

    # Act
    data = await client.async_get_electricity_rates(product_code, tariff_code, is_smart_meter, period_from, period_to)

    diff = period_to - period_from

    # Assert
    assert len(data) == diff.days * 48

    # Make sure our data is returned in 30 minute increments
    expected_valid_from = period_from
    for item in data:
        expected_valid_to = expected_valid_from + timedelta(minutes=30)

        assert "start" in item
        assert item["start"] == expected_valid_from
        assert "end" in item
        assert item["end"] == expected_valid_to

        assert "value_inc_vat" in item

        expected_value = None
        if expected_rates is not None:
            for rate in expected_rates:
                if rate["start"] <= item["start"] and rate["end"] >= item["end"]:
                    expected_value = rate["value_inc_vat"]

        if price_cap is not None:
            assert item["value_inc_vat"] <= price_cap
        elif expected_value is not None:
            assert item["value_inc_vat"] == expected_value

        expected_valid_from = expected_valid_to

    return data

@pytest.mark.asyncio
@pytest.mark.parametrize("product_code,tariff_code,price_cap,period_from,period_to",[
    ("EDF_SIMPLY_FIXED_SEP2027", "E-1R-EDF_SIMPLY_FIXED_SEP2027-A", None, datetime.strptime("2026-08-28T00:00:00Z", "%Y-%m-%dT%H:%M:%S%z"), datetime.strptime("2026-08-29T00:00:00Z", "%Y-%m-%dT%H:%M:%S%z")),
    ("EDF_SIMPLY_FIXED_2YR_SEP2028_V4", "E-1R-EDF_SIMPLY_FIXED_2YR_SEP2028_V4-A", None, datetime.strptime("2026-08-28T00:00:00Z", "%Y-%m-%dT%H:%M:%S%z"), datetime.strptime("2026-08-29T00:00:00Z", "%Y-%m-%dT%H:%M:%S%z")),
    ("EDF_STANDARD_VARIABLE", "E-1R-EDF_STANDARD_VARIABLE-A", None, datetime.strptime("2026-08-28T00:00:00Z", "%Y-%m-%dT%H:%M:%S%z"), datetime.strptime("2026-08-29T00:00:00Z", "%Y-%m-%dT%H:%M:%S%z")),
    ("EDF_SIMPLY_FIXED_SEP2027", "E-1R-EDF_SIMPLY_FIXED_SEP2027-A", 20, datetime.strptime("2026-08-28T00:00:00Z", "%Y-%m-%dT%H:%M:%S%z"), datetime.strptime("2026-08-29T00:00:00Z", "%Y-%m-%dT%H:%M:%S%z")),
    ("EDF_STANDARD_VARIABLE", "E-1R-EDF_STANDARD_VARIABLE-A", 20, datetime.strptime("2026-08-28T00:00:00Z", "%Y-%m-%dT%H:%M:%S%z"), datetime.strptime("2026-08-29T00:00:00Z", "%Y-%m-%dT%H:%M:%S%z")),
])
async def test_when_get_electricity_rates_is_called_with_tariff_then_data_is_returned_in_thirty_minute_increments(product_code, tariff_code, price_cap, period_from, period_to):
    await async_assert_electricity_data(product_code, tariff_code, False, price_cap, period_from, period_to)

@pytest.mark.asyncio
@pytest.mark.parametrize("product_code,tariff_code",[
    ("EDF_SIMPLY_FIXED_SEP2027", "E-2R-NOT-A-TARIFF-A"),
    ("EDF_SIMPLY_FIXED_SEP2027", "E-1R-NOT-A-TARIFF-A"),
    ("EDF_SIMPLY_FIXED_SEP2027", "NOT-A-TARIFF"),
    ("NOT-A-PRODUCT", "E-1R-EDF_SIMPLY_FIXED_SEP2027-A")
])
async def test_when_get_electricity_rates_is_called_for_non_existent_tariff_then_no_data_is_returned(product_code, tariff_code):
    # Arrange
    context = get_test_context()

    client = EDFEnergyApiClient(api_key=context.refresh_token or "public")

    # Act
    data = await client.async_get_electricity_rates(product_code, tariff_code, True, default_period_from, default_period_to)

    # Assert
    assert not data
