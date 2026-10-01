"""The unknown-product repair: raised only for a genuinely unknown product, and retired
once EDF publish the product again (issue #39)."""
import pytest

from custom_components.edf_energy.coordinators.account import async_check_valid_product


class FakeClient:
  def __init__(self, product):
    self._product = product
    self.asked_for = []

  async def async_get_product(self, product_code):
    self.asked_for.append(product_code)
    return self._product


def _recorders():
  raised, cleared = [], []
  return raised, cleared, (lambda code, is_elec: raised.append((code, is_elec))), (lambda code: cleared.append(code))


@pytest.mark.asyncio
async def test_unknown_product_raises_the_repair():
  raised, cleared, raise_cb, clear_cb = _recorders()

  await async_check_valid_product(FakeClient(None), "EDF_MADE_UP", True, raise_cb, clear_cb)

  assert raised == [("EDF_MADE_UP", True)]
  assert cleared == []


@pytest.mark.asyncio
async def test_known_product_clears_any_previous_repair():
  """EDF hide a withdrawn product then restore it; the notice must not outlive the problem."""
  raised, cleared, raise_cb, clear_cb = _recorders()

  await async_check_valid_product(FakeClient({"code": "EDF_REAL"}), "EDF_REAL", True, raise_cb, clear_cb)

  assert raised == []
  assert cleared == ["EDF_REAL"]


@pytest.mark.asyncio
async def test_product_synthesised_from_the_agreement_counts_as_known():
  """A hidden product the account is actually on must not raise a repair the user cannot act on."""
  raised, cleared, raise_cb, clear_cb = _recorders()
  synthesised = {"code": "EDF_EMPOWER_FIXED_EX_12M_HH", "is_from_agreement": True}

  await async_check_valid_product(FakeClient(synthesised), "EDF_EMPOWER_FIXED_EX_12M_HH", True, raise_cb, clear_cb)

  assert raised == []
  assert cleared == ["EDF_EMPOWER_FIXED_EX_12M_HH"]


@pytest.mark.asyncio
async def test_gas_product_is_reported_as_gas():
  raised, _cleared, raise_cb, clear_cb = _recorders()

  await async_check_valid_product(FakeClient(None), "EDF_GAS_THING", False, raise_cb, clear_cb)

  assert raised == [("EDF_GAS_THING", False)]


@pytest.mark.asyncio
async def test_clear_callback_is_optional():
  """Older call sites pass no clear callback and must keep working."""
  raised, _cleared, raise_cb, _clear = _recorders()

  await async_check_valid_product(FakeClient({"code": "EDF_REAL"}), "EDF_REAL", True, raise_cb)

  assert raised == []
