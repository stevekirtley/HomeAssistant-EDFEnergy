"""Turning the dashboard tabs on and off from the panel."""
import pytest

from custom_components.edf_energy import websocket_set_show_tabs
from custom_components.edf_energy.const import (
  CONFIG_ACCOUNT_ID,
  CONFIG_KIND,
  CONFIG_KIND_ACCOUNT,
  CONFIG_MAIN_SHOW_ACCOUNT_TAB,
)

ACCOUNT_ID = "A-1A2B3C4D"

class StubEntry:
  def __init__(self, options=None, data=None):
    self.entry_id = "e1"
    self.options = options if options is not None else {}
    self.data = data if data is not None else {
      CONFIG_KIND: CONFIG_KIND_ACCOUNT,
      CONFIG_ACCOUNT_ID: ACCOUNT_ID,
    }

class StubConfigEntries:
  def __init__(self, entries):
    self._entries = entries
    self.updated = []
  def async_entries(self, domain, **kwargs):
    return self._entries
  def async_update_entry(self, entry, options=None):
    entry.options = options
    self.updated.append(options)

class StubHass:
  def __init__(self, entries):
    self.config_entries = StubConfigEntries(entries)
    self.data = {}

class StubUser:
  def __init__(self, is_admin):
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

handler = getattr(websocket_set_show_tabs, "__wrapped__", websocket_set_show_tabs)

async def ask(entries, enabled, account_id=ACCOUNT_ID, is_admin=True):
  hass = StubHass(entries)
  connection = StubConnection(is_admin)
  await handler(hass, connection, {"id": 1, "account_id": account_id, "enabled": enabled})
  return connection, hass


@pytest.mark.asyncio
async def test_turning_the_tabs_on_stores_it():
  entry = StubEntry({CONFIG_MAIN_SHOW_ACCOUNT_TAB: False})

  connection, hass = await ask([entry], True)

  assert connection.error is None
  assert connection.result == {"show_account_tab": True}
  assert entry.options[CONFIG_MAIN_SHOW_ACCOUNT_TAB] == True

@pytest.mark.asyncio
async def test_turning_the_tabs_off_stores_it():
  entry = StubEntry({CONFIG_MAIN_SHOW_ACCOUNT_TAB: True})

  connection, hass = await ask([entry], False)

  assert entry.options[CONFIG_MAIN_SHOW_ACCOUNT_TAB] == False

@pytest.mark.asyncio
async def test_other_options_are_kept():
  # The panel writes one option; everything else in there belongs to somebody else.
  entry = StubEntry({CONFIG_MAIN_SHOW_ACCOUNT_TAB: True, "football_free_electricity": True})

  connection, hass = await ask([entry], False)

  assert entry.options["football_free_electricity"] == True

@pytest.mark.asyncio
async def test_a_non_admin_cannot_change_it():
  # It writes config entry options, so it is held to the same bar as the Configure form.
  entry = StubEntry({CONFIG_MAIN_SHOW_ACCOUNT_TAB: False})

  connection, hass = await ask([entry], True, is_admin=False)

  assert connection.error[0] == "unauthorized"
  assert entry.options[CONFIG_MAIN_SHOW_ACCOUNT_TAB] == False
  assert hass.config_entries.updated == []

@pytest.mark.asyncio
async def test_an_unknown_account_is_refused():
  connection, hass = await ask([StubEntry()], True, account_id="a_someoneelse")

  assert connection.error[0] == "not_found"
  assert hass.config_entries.updated == []

@pytest.mark.asyncio
async def test_a_cost_tracker_entry_is_not_written_to():
  not_an_account = StubEntry({}, {CONFIG_KIND: "cost_tracker", CONFIG_ACCOUNT_ID: ACCOUNT_ID})

  connection, hass = await ask([not_an_account], True)

  assert connection.error[0] == "not_found"
  assert hass.config_entries.updated == []
