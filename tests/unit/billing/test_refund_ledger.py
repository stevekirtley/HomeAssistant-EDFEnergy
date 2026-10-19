"""A repayment has to name the ledger it comes out of.

EDF began refusing `submitRepaymentRequest` without one after the call was already working:
`KT-CT-3821`, "Received neither ledger ID nor ledger number", errorDescription "Ledger number
should be used, as a string starting with 'L-'". The number is on neither the account nor the
billing summary, so it is read separately and sent with the request. These tests cover picking
the right ledger and, more importantly, refusing to send anything when it cannot be told -
this call moves real money, so a guess is not an option.
"""
from datetime import datetime, timezone

import pytest

from custom_components.edf_energy.api_client import EDFEnergyApiClient, RequestException
from custom_components.edf_energy.api_client.billing import main_ledger_number

NOW = datetime(2026, 10, 19, 12, 0, tzinfo=timezone.utc)
ACCOUNT_ID = "A-1A2B3C4D"


def ledgers(*rows):
  return {"data": {"account": {"ledgers": list(rows)}}}


# ── picking the ledger ───────────────────────────────────────────────────────

def test_the_ledger_marked_main_is_the_one_used():
  response = ledgers({"number": "L-AAAA1111", "ledgerType": "OTHER"},
                     {"number": "L-BBBB2222", "ledgerType": "MAIN"})

  assert main_ledger_number(response) == "L-BBBB2222"


def test_a_single_ledger_is_used_whatever_it_is_called():
  """Covers an account whose type is spelled differently from MAIN."""
  response = ledgers({"number": "L-CCCC3333", "ledgerType": "SOMETHING_ELSE"})

  assert main_ledger_number(response) == "L-CCCC3333"


def test_several_ledgers_with_none_marked_is_not_guessed():
  # Picking one at random would take money out of whichever it happened to be.
  response = ledgers({"number": "L-AAAA1111", "ledgerType": "A"},
                     {"number": "L-BBBB2222", "ledgerType": "B"})

  assert main_ledger_number(response) is None


@pytest.mark.parametrize("response", [
  None, {}, {"data": {}}, {"data": {"account": None}},
  {"data": {"account": {"ledgers": None}}}, ledgers(),
  ledgers({"ledgerType": "MAIN"}), ledgers({"number": "", "ledgerType": "MAIN"}),
])
def test_an_answer_without_a_usable_ledger_is_none(response):
  assert main_ledger_number(response) is None


# ── what gets sent ───────────────────────────────────────────────────────────

class RecordingClient(EDFEnergyApiClient):
  """Captures the GraphQL calls instead of making them."""

  def __init__(self, ledger_response):
    super().__init__(api_key="sk_test")
    self.calls = []
    self._ledger_response = ledger_response

  async def _async_graphql(self, query, variables, context, *args, **kwargs):
    self.calls.append((context, variables))
    if context == "account-ledgers":
      return self._ledger_response
    return {"data": {"submitRepaymentRequest": {
      "repaymentRequest": {"requestId": "abc-123", "status": "REQUESTED"}}}}


@pytest.mark.asyncio
async def test_the_ledger_number_is_sent_with_the_request():
  client = RecordingClient(ledgers({"number": "L-BBBB2222", "ledgerType": "MAIN"}))

  result = await client.async_submit_repayment_request(ACCOUNT_ID, 50.0, NOW)

  contexts = [c for c, _ in client.calls]
  assert contexts == ["account-ledgers", "submit-repayment"]
  sent = client.calls[1][1]["input"]
  assert sent["ledgerNumber"] == "L-BBBB2222"
  assert sent["accountNumber"] == ACCOUNT_ID
  assert sent["amountInMinorUnit"] == 5000
  assert result == {"request_id": "abc-123", "status": "REQUESTED"}


@pytest.mark.asyncio
async def test_a_ledger_passed_in_is_not_looked_up_again():
  client = RecordingClient(ledgers())

  await client.async_submit_repayment_request(ACCOUNT_ID, 50.0, NOW, ledger_number="L-DDDD4444")

  assert [c for c, _ in client.calls] == ["submit-repayment"]
  assert client.calls[0][1]["input"]["ledgerNumber"] == "L-DDDD4444"


@pytest.mark.asyncio
async def test_nothing_is_submitted_when_the_ledger_cannot_be_told():
  # The important one: EDF would refuse it anyway, but a request that cannot name its
  # ledger must not reach them at all.
  client = RecordingClient(ledgers({"number": "L-AAAA1111", "ledgerType": "A"},
                                   {"number": "L-BBBB2222", "ledgerType": "B"}))

  with pytest.raises(RequestException, match="which ledger"):
    await client.async_submit_repayment_request(ACCOUNT_ID, 50.0, NOW)

  assert [c for c, _ in client.calls] == ["account-ledgers"]


@pytest.mark.asyncio
async def test_nothing_at_all_is_sent_for_a_zero_or_negative_amount():
  client = RecordingClient(ledgers({"number": "L-BBBB2222", "ledgerType": "MAIN"}))

  for amount in (0, -10):
    with pytest.raises(RequestException, match="more than nothing"):
      await client.async_submit_repayment_request(ACCOUNT_ID, amount, NOW)

  assert client.calls == []
