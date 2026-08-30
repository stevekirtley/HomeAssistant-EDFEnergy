from datetime import datetime, timedelta
import pytest

from integration import (get_test_context)
from custom_components.edf_energy.utils.tariff_check import check_tariff_override_valid
from custom_components.edf_energy.api_client import EDFEnergyApiClient

@pytest.mark.asyncio
@pytest.mark.parametrize("original_tariff_code,tariff_code,expected_error_message",[
  ('B-1R-EDF_SIMPLY_FIXED_SEP2027-A', 'B-1R-EDF_SIMPLY_FIXED_SEP2027-A', "Unexpected energy 'B'"),
  ('E-1R-EDF_SIMPLY_FIXED_SEP2027-A', 'G-1R-EDF_SIMPLY_FIXED_SEP2027-A', "Energy must match 'E'"),
  ('G-1R-EDF_SIMPLY_FIXED_SEP2027-A', 'E-1R-EDF_SIMPLY_FIXED_SEP2027-A', "Energy must match 'G'"),
  ('E-1R-EDF_SIMPLY_FIXED_SEP2027-A', 'E-1R-EDF_SIMPLY_FIXED_SEP2027-B', "Region must match 'A'"),
  ('G-1R-EDF_SIMPLY_FIXED_SEP2027-A', 'G-1R-EDF_SIMPLY_FIXED_SEP2027-B', "Region must match 'A'"),
  ('E-1R-EDF_SIMPLY_FIXED_SEP2027-A', 'E-1R-NOT-A-PRODUCT-A', "Failed to find owning product 'NOT-A-PRODUCT'"),
  ('G-1R-EDF_SIMPLY_FIXED_SEP2027-A', 'G-1R-NOT-A-PRODUCT-A', "Failed to find owning product 'NOT-A-PRODUCT'"),
  ('E-1R-EDF_SIMPLY_FIXED_SEP2027-A', 'E-0R-EDF_SIMPLY_FIXED_2YR_SEP2028_V4-A', "Failed to find tariff 'E-0R-EDF_SIMPLY_FIXED_2YR_SEP2028_V4-A'"),
  ('G-1R-EDF_SIMPLY_FIXED_SEP2027-A', 'G-0R-EDF_STANDARD_VARIABLE-A', "Failed to find tariff 'G-0R-EDF_STANDARD_VARIABLE-A'"),
  ('E-1R-EDF_SIMPLY_FIXED_SEP2027-A', 'E-1R-EDF_STANDARD_VARIABLE-A', None),
  ('E-1R-EDF_SIMPLY_FIXED_SEP2027-A', 'E-1R-EDF_SIMPLY_FIXED_2YR_SEP2028_V4-A', None),
  ('G-1R-EDF_SIMPLY_FIXED_SEP2027-A', 'G-1R-EDF_STANDARD_VARIABLE-A', None),
])
async def test_when_data_provided_then_expected_error_is_returned(original_tariff_code, tariff_code, expected_error_message):
  # Arrange
  context = get_test_context()
  client = EDFEnergyApiClient(api_key=context.refresh_token or "public")

  # Act
  result = await check_tariff_override_valid(client, original_tariff_code, tariff_code)

  # Assert
  assert result == expected_error_message
