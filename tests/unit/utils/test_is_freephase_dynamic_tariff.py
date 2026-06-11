import pytest

from custom_components.edf_energy.utils.tariff_check import is_freephase_dynamic_tariff

@pytest.mark.asyncio
@pytest.mark.parametrize("tariff_code,expected_result",[
  ("E-1R-EDF_FREEPHASE_DYNAMIC_12M_HH-A", True),
  ("E-1R-EDF_FREEPHASE_DYNAMIC_12M_HH-C", True),
  ("E-1R-AGILE-FLEX-22-11-25-B", False),
  ("E-1R-INTELLI-VAR-22-10-14-C", False),
  ("E-1R-SUPER-GREEN-24M-21-07-30-A", False),
])
async def test_when_tariff_code_is_valid_then_correct_result_returned(tariff_code: str, expected_result: bool):
  # Act
  assert is_freephase_dynamic_tariff(tariff_code.upper()) == expected_result
  assert is_freephase_dynamic_tariff(tariff_code.lower()) == expected_result

@pytest.mark.asyncio
async def test_when_invalid_then_false_returned():
  # Act
  assert is_freephase_dynamic_tariff("invalid-tariff-code") == False
