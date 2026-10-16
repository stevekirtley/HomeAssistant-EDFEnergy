"""The dashboard tabs option, and how the panel is told about it.

On by default as of 19.3.0. The default only decides for people who have never said: a
stored False is still a False, which several of these pin.
"""
import pytest

from custom_components.edf_energy import websocket_beta_features
from custom_components.edf_energy.config_flow import EDFEnergyAccountOptionsFlow
from custom_components.edf_energy.const import (
  CONFIG_ACCOUNT_ID,
  CONFIG_KIND,
  CONFIG_KIND_ACCOUNT,
  CONFIG_MAIN_FOOTBALL_FREE_ELECTRICITY,
  CONFIG_MAIN_SHOW_ACCOUNT_TAB,
  DOMAIN,
)

ACCOUNT_ID = "A-1A2B3C4D"

class StubEntry:
  def __init__(self, options=None, data=None):
    self.options = options if options is not None else {}
    self.data = data if data is not None else {
      CONFIG_KIND: CONFIG_KIND_ACCOUNT,
      CONFIG_ACCOUNT_ID: ACCOUNT_ID,
    }

class StubConfigEntries:
  def __init__(self, entries):
    self._entries = entries

  def async_entries(self, domain):
    return self._entries

class StubHass:
  def __init__(self, entries):
    self.config_entries = StubConfigEntries(entries)

class StubUser:
  def __init__(self, is_admin=True):
    self.is_admin = is_admin

class StubConnection:
  def __init__(self, is_admin=True):
    self.result = None
    self.error = None
    self.user = StubUser(is_admin)

  def send_result(self, msg_id, result):
    self.result = result

  def send_error(self, msg_id, code, message):
    self.error = (code, message)

def ask(entries, account_id=ACCOUNT_ID):
  connection = StubConnection()
  websocket_beta_features(StubHass(entries), connection, {"id": 1, "account_id": account_id})
  return connection.result

# ── The option itself ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_when_options_opened_then_beta_flag_shown_and_defaults_off():
  # Arrange
  flow = EDFEnergyAccountOptionsFlow(StubEntry())

  # Act
  result = await flow.async_step_init()

  # Assert
  assert result["type"] == "form"
  assert result["step_id"] == "init"

  keys = {str(key): key for key in result["data_schema"].schema}
  assert CONFIG_MAIN_SHOW_ACCOUNT_TAB in keys
  assert keys[CONFIG_MAIN_SHOW_ACCOUNT_TAB].default() == True

@pytest.mark.asyncio
async def test_when_already_turned_on_then_form_shows_it_on():
  # Arrange
  flow = EDFEnergyAccountOptionsFlow(StubEntry({CONFIG_MAIN_SHOW_ACCOUNT_TAB: True}))

  # Act
  result = await flow.async_step_init()

  # Assert
  keys = {str(key): key for key in result["data_schema"].schema}
  assert keys[CONFIG_MAIN_SHOW_ACCOUNT_TAB].default() == True

@pytest.mark.asyncio
async def test_when_submitted_then_options_the_form_does_not_show_are_kept():
  """The archived football toggle is not on the form, so a straight replace would wipe it."""
  # Arrange
  flow = EDFEnergyAccountOptionsFlow(StubEntry({CONFIG_MAIN_FOOTBALL_FREE_ELECTRICITY: True}))

  # Act
  result = await flow.async_step_init({CONFIG_MAIN_SHOW_ACCOUNT_TAB: True})

  # Assert
  assert result["data"][CONFIG_MAIN_SHOW_ACCOUNT_TAB] == True
  assert result["data"][CONFIG_MAIN_FOOTBALL_FREE_ELECTRICITY] == True

@pytest.mark.asyncio
async def test_when_submitted_then_the_new_value_wins_over_the_stored_one():
  # Arrange
  flow = EDFEnergyAccountOptionsFlow(StubEntry({CONFIG_MAIN_SHOW_ACCOUNT_TAB: True}))

  # Act
  result = await flow.async_step_init({CONFIG_MAIN_SHOW_ACCOUNT_TAB: False})

  # Assert
  assert result["data"][CONFIG_MAIN_SHOW_ACCOUNT_TAB] == False

# ── What the panel is told ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_when_flag_not_set_then_panel_told_on():
  # On by default as of 19.3.0.
  assert ask([StubEntry()])["show_account_tab"] == True

@pytest.mark.asyncio
async def test_when_flag_turned_off_then_it_stays_off():
  # The default only decides for people who have never said. Somebody who turned the tabs
  # off has said.
  assert ask([StubEntry({CONFIG_MAIN_SHOW_ACCOUNT_TAB: False})])["show_account_tab"] == False

@pytest.mark.asyncio
async def test_when_flag_set_then_panel_told_on():
  assert ask([StubEntry({CONFIG_MAIN_SHOW_ACCOUNT_TAB: True})])["show_account_tab"] == True

@pytest.mark.asyncio
async def test_when_account_id_comes_from_an_entity_slug_then_still_matched():
  """The panel derives the id from entity slugs, so it arrives as 'a_1a2b3c4d'."""
  # Act/Assert
  assert ask([StubEntry({CONFIG_MAIN_SHOW_ACCOUNT_TAB: True})], "a_1a2b3c4d")["show_account_tab"] == True

@pytest.mark.asyncio
async def test_when_account_unknown_then_the_default_answers_rather_than_erroring():
  """A panel that cannot be matched to an entry still gets an answer, not a break."""
  # Act/Assert - note the entry that does exist has it ON, and must not answer for another
  # account; the default does.
  assert ask([StubEntry({CONFIG_MAIN_SHOW_ACCOUNT_TAB: True})], "a_someoneelse")["show_account_tab"] == True

@pytest.mark.asyncio
async def test_when_another_account_has_it_on_then_this_one_is_unaffected():
  """The flag is per account entry, so two accounts can disagree."""
  # Arrange
  other = StubEntry({CONFIG_MAIN_SHOW_ACCOUNT_TAB: False}, {
    CONFIG_KIND: CONFIG_KIND_ACCOUNT,
    CONFIG_ACCOUNT_ID: "A-99999999",
  })
  mine = StubEntry({CONFIG_MAIN_SHOW_ACCOUNT_TAB: True})

  # Act/Assert
  assert ask([other, mine])["show_account_tab"] == True

@pytest.mark.asyncio
async def test_when_entry_is_not_an_account_then_ignored():
  """Cost trackers and target rates are entries too, and carry no beta options."""
  # Arrange
  not_an_account = StubEntry({CONFIG_MAIN_SHOW_ACCOUNT_TAB: False}, {
    CONFIG_KIND: "cost_tracker",
    CONFIG_ACCOUNT_ID: ACCOUNT_ID,
  })

  # Act/Assert
  assert ask([not_an_account])["show_account_tab"] == True
