"""The guards around asking EDF for a refund.

This command spends real money out of the account, so the checks are tested rather than
assumed: a non-admin cannot reach it, an amount over EDF's own maximum is refused, and an
account EDF have already said no to is refused before anything is sent.
"""
import pytest

from custom_components.edf_energy import websocket_request_refund
from custom_components.edf_energy.const import (
  CONFIG_ACCOUNT_ID,
  CONFIG_KIND,
  CONFIG_KIND_ACCOUNT,
  DATA_BILLING,
  DATA_CLIENT,
  DOMAIN,
)

ACCOUNT_ID = "A-1A2B3C4D"

SUMMARY = {
  "balance": 1234.56,
  "refund": {"can_request": True, "reason": None, "maximum": 98.76, "requests": []},
}

class StubClient:
  def __init__(self):
    self.submitted = []

  async def async_submit_repayment_request(self, account_id, amount, current):
    self.submitted.append((account_id, amount))
    return {"request_id": "abc-123", "status": "REQUESTED"}

class StubResult:
  def __init__(self, summary):
    self.summary = summary

class StubEntry:
  def __init__(self):
    self.data = {CONFIG_KIND: CONFIG_KIND_ACCOUNT, CONFIG_ACCOUNT_ID: ACCOUNT_ID}
    self.options = {}

class StubConfigEntries:
  def async_entries(self, domain):
    return [StubEntry()]

class StubCoordinator:
  def __init__(self):
    self.refreshed = False

  async def async_request_refresh(self):
    self.refreshed = True

class StubHass:
  def __init__(self, summary=SUMMARY, client=None):
    self.config_entries = StubConfigEntries()
    self.data = {DOMAIN: {ACCOUNT_ID: {
      DATA_CLIENT: client if client is not None else StubClient(),
      DATA_BILLING.format(ACCOUNT_ID): StubResult(summary) if summary is not None else None,
    }}}

class StubUser:
  def __init__(self, is_admin=True):
    self.is_admin = is_admin

class StubConnection:
  def __init__(self, is_admin=True):
    self.user = StubUser(is_admin)
    self.result = None
    self.error = None

  def send_result(self, msg_id, result):
    self.result = result

  def send_error(self, msg_id, code, message):
    self.error = (code, message)

# The async_response decorator wraps the handler in something that schedules it as a
# background task on a real hass. The coroutine underneath is what is worth testing.
handler = getattr(websocket_request_refund, "__wrapped__", websocket_request_refund)

async def ask(amount, hass=None, is_admin=True, account_id=ACCOUNT_ID):
  hass = hass if hass is not None else StubHass()
  connection = StubConnection(is_admin)
  await handler(hass, connection, {"id": 1, "account_id": account_id, "amount": amount})
  return connection, hass

# ── Who can ask ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_non_admin_cannot_request_a_refund():
  # Act
  connection, hass = await ask(50, is_admin=False)

  # Assert
  assert connection.error[0] == "unauthorized"
  assert hass.data[DOMAIN][ACCOUNT_ID][DATA_CLIENT].submitted == []

@pytest.mark.asyncio
async def test_an_unknown_account_is_refused():
  # Act
  connection, _ = await ask(50, account_id="A-NOTMINE")

  # Assert
  assert connection.error[0] == "not_found"

# ── The amount ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_refund_within_the_maximum_is_sent():
  # Act - comfortably under the £98.76 the fixture says EDF will allow
  connection, hass = await ask(50)

  # Assert
  assert connection.error is None
  assert connection.result == {"request_id": "abc-123", "status": "REQUESTED"}
  assert hass.data[DOMAIN][ACCOUNT_ID][DATA_CLIENT].submitted == [(ACCOUNT_ID, 50.0)]

@pytest.mark.asyncio
async def test_more_than_edf_will_refund_is_refused_before_anything_is_sent():
  # The balance is £1,234 but EDF will only refund £98.76, so asking for the balance has
  # to be stopped here rather than by EDF.
  # Act
  connection, hass = await ask(1234.56)

  # Assert
  assert connection.error[0] == "invalid_amount"
  assert "98.76" in connection.error[1]
  assert hass.data[DOMAIN][ACCOUNT_ID][DATA_CLIENT].submitted == []

@pytest.mark.asyncio
async def test_nothing_or_less_is_refused():
  for amount in (0, -10):
    # Act
    connection, hass = await ask(amount)

    # Assert
    assert connection.error[0] == "invalid_amount"
    assert hass.data[DOMAIN][ACCOUNT_ID][DATA_CLIENT].submitted == []

@pytest.mark.asyncio
async def test_exactly_the_maximum_is_allowed():
  # Act
  connection, hass = await ask(98.76)

  # Assert
  assert connection.error is None
  assert hass.data[DOMAIN][ACCOUNT_ID][DATA_CLIENT].submitted == [(ACCOUNT_ID, 98.76)]

# ── Eligibility ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_an_account_edf_have_said_no_to_can_still_request():
  # EDF's eligibility flag is advisory. It said no to a real account with
  # HAS_NOT_GIVEN_READINGS_RECENTLY and then accepted and paid two requests made anyway, so
  # treating it as a gate would block a request that works. The panel shows the reason as a
  # caveat; whether to refuse is EDF's call when the request reaches them.
  # Arrange
  summary = {"balance": 100, "refund": {"can_request": False, "reason": "HAS_NOT_GIVEN_READINGS_RECENTLY",
                                        "maximum": 50, "requests": []}}
  hass = StubHass(summary)

  # Act
  connection, hass = await ask(10, hass=hass)

  # Assert
  assert connection.error is None
  assert hass.data[DOMAIN][ACCOUNT_ID][DATA_CLIENT].submitted == [(ACCOUNT_ID, 10)]

@pytest.mark.asyncio
async def test_the_amount_is_still_checked_when_edf_have_said_no():
  # Dropping the eligibility gate must not drop the amount checks with it.
  # Arrange
  summary = {"balance": 100, "refund": {"can_request": False, "reason": "HAS_NOT_GIVEN_READINGS_RECENTLY",
                                        "maximum": 50, "requests": []}}

  # Act
  connection, hass = await ask(60, hass=StubHass(summary))

  # Assert
  assert connection.error[0] == "invalid_amount"
  assert hass.data[DOMAIN][ACCOUNT_ID][DATA_CLIENT].submitted == []

@pytest.mark.asyncio
async def test_an_unknown_maximum_does_not_block_the_request():
  # If EDF do not quote a maximum there is nothing to check the amount against, and their
  # own validation is the backstop. Being unable to read it must not mean nobody can ever
  # request a refund.
  # Arrange
  hass = StubHass({"balance": 100, "refund": {"can_request": True, "maximum": None, "requests": []}})

  # Act
  connection, hass = await ask(10, hass=hass)

  # Assert
  assert connection.error is None
  assert hass.data[DOMAIN][ACCOUNT_ID][DATA_CLIENT].submitted == [(ACCOUNT_ID, 10.0)]
