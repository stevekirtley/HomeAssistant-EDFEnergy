import pytest

from custom_components.edf_energy.api_client import get_standing_charge

def __charge(value_inc_vat: float, payment_method):
  return {
    "value_exc_vat": value_inc_vat,
    "value_inc_vat": value_inc_vat,
    "valid_from": "2026-06-04T23:00:00Z",
    "valid_to": "2026-06-05T23:00:00Z",
    "payment_method": payment_method,
  }

@pytest.mark.asyncio
async def test_direct_debit_only_standing_charge_returned_when_not_favouring_direct_debit():
  # A tariff that only publishes a DIRECT_DEBIT standing charge must still return it
  # when the user has not favoured direct debit rates.
  result = get_standing_charge([__charge(50.0, "DIRECT_DEBIT")], "test_tariff", favour_direct_debit_rates=False)

  assert result is not None
  assert result["value_inc_vat"] == 50.0

@pytest.mark.asyncio
async def test_null_payment_method_standing_charge_always_returned():
  result = get_standing_charge([__charge(59.72295, None)], "test_tariff", favour_direct_debit_rates=False)

  assert result is not None
  assert result["value_inc_vat"] == 59.72295

@pytest.mark.asyncio
async def test_mixed_payment_methods_standing_charge_honours_the_favour_preference():
  data = [__charge(40.0, "DIRECT_DEBIT"), __charge(45.0, "NON_DIRECT_DEBIT")]

  favouring_direct_debit = get_standing_charge(data, "test_tariff", favour_direct_debit_rates=True)
  assert favouring_direct_debit is not None
  assert favouring_direct_debit["value_inc_vat"] == 40.0

  not_favouring_direct_debit = get_standing_charge(data, "test_tariff", favour_direct_debit_rates=False)
  assert not_favouring_direct_debit is not None
  assert not_favouring_direct_debit["value_inc_vat"] == 45.0
