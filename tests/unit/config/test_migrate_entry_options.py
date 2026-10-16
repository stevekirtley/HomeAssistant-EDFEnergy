"""What a config entry migration does to the options stored on it.

Options used to be wiped on every migration. That was right once - the move off
options-based configuration copied them into data first, so clearing them finished the
job - but it has outlived that: options now hold live settings, and the dashboard tabs
flag is one of them. Wiping on a version bump would hand somebody back a default they had
already turned off.
"""
import pytest

import custom_components.edf_energy as integration
from custom_components.edf_energy import async_migrate_entry
from custom_components.edf_energy.const import (
  CONFIG_ACCOUNT_ID,
  CONFIG_KIND,
  CONFIG_KIND_ACCOUNT,
  CONFIG_MAIN_SHOW_ACCOUNT_TAB,
  CONFIG_VERSION,
)

ACCOUNT_ID = "A-1A2B3C4D"


class StubEntry:
  def __init__(self, version, options=None, data=None):
    self.version = version
    self.entry_id = "e1"
    self.title = "old title"
    self.options = options if options is not None else {}
    self.data = data if data is not None else {
      CONFIG_KIND: CONFIG_KIND_ACCOUNT,
      CONFIG_ACCOUNT_ID: ACCOUNT_ID,
    }

class StubConfigEntries:
  def __init__(self):
    self.updates = []
  def async_update_entry(self, entry, title=None, data=None, options=None, version=None):
    entry.title = title
    entry.data = data
    entry.options = options
    entry.version = version
    self.updates.append({"options": options, "data": data, "version": version})
  def async_entries(self, *args, **kwargs):
    return []

class StubHass:
  def __init__(self):
    self.config_entries = StubConfigEntries()


@pytest.fixture(autouse=True)
def _passthrough_main_config(monkeypatch):
  # The per-kind migrations have their own tests; these cases are about the options.
  async def passthrough(version, data, *args):
    return data
  monkeypatch.setattr(integration, "async_migrate_main_config", passthrough)


@pytest.mark.asyncio
async def test_an_entry_already_current_is_left_alone():
  hass = StubHass()
  entry = StubEntry(CONFIG_VERSION, {CONFIG_MAIN_SHOW_ACCOUNT_TAB: False})

  await async_migrate_entry(hass, entry)

  assert hass.config_entries.updates == []
  assert entry.options == {CONFIG_MAIN_SHOW_ACCOUNT_TAB: False}

@pytest.mark.asyncio
async def test_options_are_cleared_when_they_were_copied_into_data():
  # Version 8 and below kept configuration in options; the migration moves it into data,
  # so clearing options afterwards is part of that move rather than a loss.
  hass = StubHass()
  entry = StubEntry(8, {"api_key": "abc123"})

  await async_migrate_entry(hass, entry)

  assert hass.config_entries.updates[0]["options"] == {}
  assert hass.config_entries.updates[0]["data"]["api_key"] == "abc123"

@pytest.mark.asyncio
async def test_a_later_migration_keeps_the_options(monkeypatch):
  # The case this exists for: a future version bump must not reset a setting somebody has
  # chosen. Nothing copies options into data at this point, so clearing them is pure loss.
  monkeypatch.setattr(integration, "CONFIG_VERSION", CONFIG_VERSION + 1)
  hass = StubHass()
  entry = StubEntry(CONFIG_VERSION, {CONFIG_MAIN_SHOW_ACCOUNT_TAB: False})

  await async_migrate_entry(hass, entry)

  assert hass.config_entries.updates[0]["options"] == {CONFIG_MAIN_SHOW_ACCOUNT_TAB: False}
  assert entry.options[CONFIG_MAIN_SHOW_ACCOUNT_TAB] == False

@pytest.mark.asyncio
async def test_a_later_migration_with_no_options_is_fine(monkeypatch):
  monkeypatch.setattr(integration, "CONFIG_VERSION", CONFIG_VERSION + 1)
  hass = StubHass()
  entry = StubEntry(CONFIG_VERSION, {})

  await async_migrate_entry(hass, entry)

  assert hass.config_entries.updates[0]["options"] == {}

@pytest.mark.asyncio
async def test_the_entry_is_moved_to_the_current_version(monkeypatch):
  monkeypatch.setattr(integration, "CONFIG_VERSION", CONFIG_VERSION + 1)
  hass = StubHass()
  entry = StubEntry(CONFIG_VERSION, {CONFIG_MAIN_SHOW_ACCOUNT_TAB: True})

  await async_migrate_entry(hass, entry)

  assert hass.config_entries.updates[0]["version"] == CONFIG_VERSION + 1
