import pytest

from custom_components.edf_energy import DISPLAY_ONLY_OPTIONS, _changed_options, options_update_listener
from custom_components.edf_energy.const import (
  CONFIG_MAIN_SHOW_ACCOUNT_TAB,
  CONFIG_MAIN_API_KEY,
  DOMAIN,
)


class StubEntry:
  def __init__(self, options, entry_id="e1"):
    self.entry_id = entry_id
    self.options = options
    # A kind the listener will not try to chase child entries for.
    self.data = {"kind": "unknown"}

class StubConfigEntries:
  def __init__(self):
    self.reloaded = []
  async def async_reload(self, entry_id):
    self.reloaded.append(entry_id)

class StubHass:
  def __init__(self):
    self.data = {DOMAIN: {}}
    self.config_entries = StubConfigEntries()


def test_the_display_flag_is_treated_as_display_only():
  assert CONFIG_MAIN_SHOW_ACCOUNT_TAB in DISPLAY_ONLY_OPTIONS

def test_an_entry_never_seen_reports_that_it_does_not_know():
  # None means "no idea", not "nothing changed" - the listener reloads on it. Returning the
  # key set instead would skip the reload for an entry whose only options are display ones,
  # which is a reload skipped on no evidence at all.
  hass = StubHass()
  entry = StubEntry({CONFIG_MAIN_SHOW_ACCOUNT_TAB: True, "other": 1})

  assert _changed_options(hass, entry) is None

def test_changes_are_measured_against_what_was_last_seen():
  hass = StubHass()
  entry = StubEntry({CONFIG_MAIN_SHOW_ACCOUNT_TAB: True})
  _changed_options(hass, entry)                       # first sight, remembered

  entry.options = {CONFIG_MAIN_SHOW_ACCOUNT_TAB: False}

  assert _changed_options(hass, entry) == {CONFIG_MAIN_SHOW_ACCOUNT_TAB}

def test_a_key_that_appears_counts_as_changed():
  hass = StubHass()
  entry = StubEntry({})
  _changed_options(hass, entry)

  entry.options = {CONFIG_MAIN_SHOW_ACCOUNT_TAB: True}

  assert _changed_options(hass, entry) == {CONFIG_MAIN_SHOW_ACCOUNT_TAB}

def test_a_key_that_disappears_counts_as_changed():
  hass = StubHass()
  entry = StubEntry({CONFIG_MAIN_SHOW_ACCOUNT_TAB: True})
  _changed_options(hass, entry)

  entry.options = {}

  assert _changed_options(hass, entry) == {CONFIG_MAIN_SHOW_ACCOUNT_TAB}

def test_nothing_changing_is_not_a_change():
  hass = StubHass()
  entry = StubEntry({CONFIG_MAIN_SHOW_ACCOUNT_TAB: True})
  _changed_options(hass, entry)

  assert _changed_options(hass, entry) == set()


# ── What the listener does about it ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_flipping_only_the_display_flag_does_not_reload():
  # The whole point: a reload drops every entity for a moment, which is far too much for a
  # switch somebody is flicking to look at a layout.
  hass = StubHass()
  entry = StubEntry({CONFIG_MAIN_SHOW_ACCOUNT_TAB: True})
  _changed_options(hass, entry)
  entry.options = {CONFIG_MAIN_SHOW_ACCOUNT_TAB: False}

  await options_update_listener(hass, entry)

  assert hass.config_entries.reloaded == []

@pytest.mark.asyncio
async def test_a_real_option_still_reloads():
  hass = StubHass()
  entry = StubEntry({CONFIG_MAIN_SHOW_ACCOUNT_TAB: True, CONFIG_MAIN_API_KEY: "old"})
  _changed_options(hass, entry)
  entry.options = {CONFIG_MAIN_SHOW_ACCOUNT_TAB: True, CONFIG_MAIN_API_KEY: "new"}

  await options_update_listener(hass, entry)

  assert hass.config_entries.reloaded == ["e1"]

@pytest.mark.asyncio
async def test_a_real_option_moving_alongside_the_display_flag_still_reloads():
  # The skip only applies when nothing else moved - otherwise a real change could ride in
  # unnoticed beside a harmless one.
  hass = StubHass()
  entry = StubEntry({CONFIG_MAIN_SHOW_ACCOUNT_TAB: True, CONFIG_MAIN_API_KEY: "old"})
  _changed_options(hass, entry)
  entry.options = {CONFIG_MAIN_SHOW_ACCOUNT_TAB: False, CONFIG_MAIN_API_KEY: "new"}

  await options_update_listener(hass, entry)

  assert hass.config_entries.reloaded == ["e1"]

@pytest.mark.asyncio
async def test_an_unseen_entry_reloads():
  hass = StubHass()
  entry = StubEntry({CONFIG_MAIN_SHOW_ACCOUNT_TAB: False})

  await options_update_listener(hass, entry)

  assert hass.config_entries.reloaded == ["e1"]
