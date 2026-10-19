"""Replacing an older access token with a durable API key, only when the user agrees.

Minting is the only way to get a usable key out of EDF - the readable liveSecretKey is
masked - and it invalidates any key already issued on the account, so another application
holding that key stops working. Up to 20.1.0 this happened silently at startup; now it is a
repair the user confirms. These tests cover the part that spends that one-shot action: that
nothing is minted without confirmation, that a key is verified before the old token is let
go, and that a failure anywhere leaves the entry exactly as it was.
"""
import pytest

from custom_components.edf_energy.const import (
  CONFIG_ACCOUNT_ID,
  CONFIG_KIND,
  CONFIG_KIND_ACCOUNT,
  CONFIG_MAIN_API_KEY,
  CONFIG_MAIN_REFRESH_EXPIRES_IN,
  CONFIG_MAIN_REFRESH_TOKEN,
  DOMAIN,
  REPAIR_API_KEY_NEEDED,
)
from custom_components.edf_energy.repairs import ApiKeyNeededRepairFlow, async_create_fix_flow
from custom_components.edf_energy.utils.repairs import safe_repair_key

ACCOUNT_ID = "A-XXXXXX"
NEW_KEY = "sk_live_the_new_one"


class StubEntry:
  def __init__(self, data):
    self.entry_id = "entry-1"
    self.data = data
    self.options = {}


class StubConfigEntries:
  def __init__(self, entries):
    self._entries = entries
    self.reloaded = []

  def async_entries(self, domain):
    return self._entries

  def async_update_entry(self, entry, data=None, options=None):
    if data is not None:
      entry.data = data
    if options is not None:
      entry.options = options

  async def async_reload(self, entry_id):
    self.reloaded.append(entry_id)


class StubHass:
  def __init__(self, entries):
    self.config_entries = StubConfigEntries(entries)


class StubClient:
  """Stands in for both the minting client and the verifying client."""

  created = []

  def __init__(self, refresh_token=None, api_key=None, **kwargs):
    self.refresh_token = refresh_token
    self.api_key = api_key
    self.closed = False
    StubClient.created.append(self)

  async def async_ensure_api_key(self):
    if StubClient.mint_error is not None:
      raise StubClient.mint_error
    return NEW_KEY

  async def async_refresh_token(self):
    if StubClient.verify_error is not None:
      raise StubClient.verify_error

  async def async_close(self):
    self.closed = True


@pytest.fixture(autouse=True)
def stub_client(monkeypatch):
  StubClient.created = []
  StubClient.mint_error = None
  StubClient.verify_error = None
  monkeypatch.setattr("custom_components.edf_energy.repairs.EDFEnergyApiClient", StubClient)
  return StubClient


@pytest.fixture(autouse=True)
def captured_issues(monkeypatch):
  deleted = []
  monkeypatch.setattr(
    "custom_components.edf_energy.repairs.ir.async_delete_issue",
    lambda hass, domain, issue_id: deleted.append((domain, issue_id)),
  )
  return deleted


def _flow(entry_data=None):
  entry = StubEntry({
    CONFIG_KIND: CONFIG_KIND_ACCOUNT,
    CONFIG_ACCOUNT_ID: ACCOUNT_ID,
    **(entry_data if entry_data is not None else {
      CONFIG_MAIN_REFRESH_TOKEN: "old-token",
      CONFIG_MAIN_REFRESH_EXPIRES_IN: 1234567890,
    }),
  })
  flow = ApiKeyNeededRepairFlow({"account_id": ACCOUNT_ID})
  flow.hass = StubHass([entry])
  return flow, entry


# ── nothing happens until the user says so ───────────────────────────────────

@pytest.mark.asyncio
async def test_the_first_step_only_asks_and_mints_nothing():
  # Arrange
  flow, entry = _flow()

  # Act
  result = await flow.async_step_init()

  # Assert
  assert result["type"] == "form"
  assert result["step_id"] == "confirm"
  assert result["description_placeholders"]["account_id"] == ACCOUNT_ID
  assert StubClient.created == []
  assert entry.data[CONFIG_MAIN_REFRESH_TOKEN] == "old-token"


@pytest.mark.asyncio
async def test_the_dispatcher_routes_the_issue_to_this_flow():
  # Act
  flow = await async_create_fix_flow(
    None, safe_repair_key(REPAIR_API_KEY_NEEDED, ACCOUNT_ID), {"account_id": ACCOUNT_ID}
  )

  # Assert
  assert isinstance(flow, ApiKeyNeededRepairFlow)


# ── confirming it ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_confirming_stores_the_key_and_drops_the_old_token(captured_issues):
  # Arrange
  flow, entry = _flow()

  # Act
  result = await flow.async_step_confirm({})

  # Assert
  assert result["type"] == "create_entry"
  assert entry.data[CONFIG_MAIN_API_KEY] == NEW_KEY
  assert CONFIG_MAIN_REFRESH_TOKEN not in entry.data
  assert CONFIG_MAIN_REFRESH_EXPIRES_IN not in entry.data
  assert flow.hass.config_entries.reloaded == ["entry-1"]
  assert captured_issues == [(DOMAIN, safe_repair_key(REPAIR_API_KEY_NEEDED, ACCOUNT_ID))]


@pytest.mark.asyncio
async def test_the_key_is_verified_before_the_old_token_is_let_go():
  # Arrange - the minting client is built from the token, the verifying one from the key
  flow, _ = _flow()

  # Act
  await flow.async_step_confirm({})

  # Assert
  assert [(c.refresh_token, c.api_key) for c in StubClient.created] == [
    ("old-token", None),
    (None, NEW_KEY),
  ]
  assert all(c.closed for c in StubClient.created)


# ── when it goes wrong, nothing is lost ──────────────────────────────────────

@pytest.mark.asyncio
async def test_a_refused_mint_leaves_the_entry_untouched(captured_issues):
  # Arrange
  StubClient.mint_error = Exception("EDF said no")
  flow, entry = _flow()

  # Act
  result = await flow.async_step_confirm({})

  # Assert
  assert result["type"] == "abort"
  assert result["reason"] == "api_key_failed"
  assert entry.data[CONFIG_MAIN_REFRESH_TOKEN] == "old-token"
  assert CONFIG_MAIN_API_KEY not in entry.data
  assert captured_issues == []


@pytest.mark.asyncio
async def test_a_key_that_fails_verification_is_not_stored(captured_issues):
  # A key that does not authenticate must never replace a token that does, or the entry is
  # left with no working credential at all.
  # Arrange
  StubClient.verify_error = Exception("not authorised")
  flow, entry = _flow()

  # Act
  result = await flow.async_step_confirm({})

  # Assert
  assert result["type"] == "abort"
  assert result["reason"] == "api_key_failed"
  assert entry.data[CONFIG_MAIN_REFRESH_TOKEN] == "old-token"
  assert CONFIG_MAIN_API_KEY not in entry.data
  assert flow.hass.config_entries.reloaded == []
  assert captured_issues == []


@pytest.mark.asyncio
async def test_both_clients_are_closed_even_when_verification_fails():
  # Arrange
  StubClient.verify_error = Exception("not authorised")
  flow, _ = _flow()

  # Act
  await flow.async_step_confirm({})

  # Assert
  assert all(c.closed for c in StubClient.created)


# ── the prompt can go stale ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_an_entry_that_already_has_a_key_just_clears_the_prompt(captured_issues):
  # Somebody can re-authenticate through the normal flow while the repair sits unread.
  # Arrange
  flow, entry = _flow({CONFIG_MAIN_API_KEY: "sk_live_already_here"})

  # Act
  result = await flow.async_step_confirm({})

  # Assert
  assert result["type"] == "create_entry"
  assert entry.data[CONFIG_MAIN_API_KEY] == "sk_live_already_here"
  assert StubClient.created == []
  assert captured_issues == [(DOMAIN, safe_repair_key(REPAIR_API_KEY_NEEDED, ACCOUNT_ID))]


@pytest.mark.asyncio
async def test_an_account_that_has_gone_away_aborts():
  # Arrange
  flow = ApiKeyNeededRepairFlow({"account_id": ACCOUNT_ID})
  flow.hass = StubHass([])

  # Act
  result = await flow.async_step_confirm({})

  # Assert
  assert result["type"] == "abort"
  assert result["reason"] == "account_not_found"
  assert StubClient.created == []
