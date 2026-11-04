"""A diagnostics download has to work when the entry is broken, which is when it is wanted.

Reported as issue #53 on 21.0.0: an install where 38 cost tracker entries had lost their
kind and their account id, every one failing to set up. Asking for diagnostics was useless,
because the handler read the account id and the set up account straight out of the entry and
raised a KeyError of its own - so the one person who could have shown us what was actually on
those entries had nothing to send.

What comes back instead is the shape of every entry rather than its contents, which is the
thing no log will ever show, and nothing identifying with it.
"""
from custom_components.edfenergy_uk.const import (
  CONFIG_ACCOUNT_ID,
  DATA_ACCOUNT,
  DATA_CLIENT,
  DOMAIN,
)
from custom_components.edfenergy_uk.diagnostics import _async_broken_entry_diagnostics


class FakeEntry:
  def __init__(self, data, entry_id="entry-1", unique_id=None, title="A-XXXXXX", options=None):
    self.data = dict(data)
    self.options = dict(options or {})
    self.entry_id = entry_id
    self.unique_id = unique_id
    self.title = title
    self.version = 9
    self.minor_version = 1
    self.source = "user"
    self.disabled_by = None
    self.state = "not_loaded"


class FakeConfigEntries:
  def __init__(self, entries):
    self._entries = entries

  def async_entries(self, domain, include_ignore=False):
    return self._entries


class FakeHass:
  def __init__(self, entries, data=None):
    self.config_entries = FakeConfigEntries(entries)
    self.data = data if data is not None else {}


def test_a_healthy_entry_reports_normally():
  """It must not divert the normal download, which is almost every download."""
  entry = FakeEntry({CONFIG_ACCOUNT_ID: "A-XXXXXX"})
  hass = FakeHass([entry], {DOMAIN: {"A-XXXXXX": {DATA_ACCOUNT: object(), DATA_CLIENT: object()}}})

  assert _async_broken_entry_diagnostics(hass, entry, dict(entry.data)) is None


def test_an_entry_with_no_account_id_still_produces_a_download():
  """The reported case. Before this it raised KeyError: 'account_id' instead."""
  broken = FakeEntry({}, entry_id="broken", unique_id="edf_energy_ct_A-XXXXXX_sensor.x")
  hass = FakeHass([broken], {})

  result = _async_broken_entry_diagnostics(hass, broken, dict(broken.data))

  assert result is not None
  assert result["entry_not_reportable"]["reason"] == "no account id recorded on the entry"


def test_an_account_that_failed_to_set_up_still_produces_a_download():
  """The account entry carries its id but never finished, so hass.data has nothing."""
  entry = FakeEntry({CONFIG_ACCOUNT_ID: "A-XXXXXX"})
  hass = FakeHass([entry], {DOMAIN: {}})

  result = _async_broken_entry_diagnostics(hass, entry, dict(entry.data))

  assert result is not None
  assert result["entry_not_reportable"]["reason"] == "the account this entry belongs to is not set up"


def test_every_entrys_keys_are_reported_because_that_is_what_identifies_the_fault():
  """Which keys an entry carries is the whole question, and no log shows it."""
  account = FakeEntry({CONFIG_ACCOUNT_ID: "A-XXXXXX", "kind": "account"}, entry_id="account")
  broken = FakeEntry({}, entry_id="broken", unique_id="edf_energy_ct_A-XXXXXX_sensor.x")
  hass = FakeHass([account, broken], {})

  reported = _async_broken_entry_diagnostics(hass, broken, dict(broken.data))["entry_not_reportable"]["entries"]

  assert [item["entry_id"] for item in reported] == ["account", "broken"]
  assert reported[0]["keys"] == ["account_id", "kind"]
  assert reported[1]["keys"] == []
  # Whether the unique id is a cost tracker suggestion's is the other half of the answer.
  assert reported[0]["has_unique_id"] is False
  assert reported[1]["unique_id_is_discovered_cost_tracker"] is True


def test_nothing_identifying_goes_into_the_report():
  """These files get attached to public issues.

  A cost tracker's title and its unique id both spell the account id out in full, so neither
  is reported - only whether a unique id exists and whether it is one we could rebuild from.
  """
  broken = FakeEntry({CONFIG_ACCOUNT_ID: "A-XXXXXX"}, entry_id="broken",
                     unique_id="edf_energy_ct_A-XXXXXX_sensor.x",
                     title="Tracked Energy Cost Tracker (A-XXXXXX)")
  hass = FakeHass([broken], {DOMAIN: {}})

  result = _async_broken_entry_diagnostics(hass, broken, dict(broken.data))

  assert "A-XXXXXX" not in repr(result)
  assert "Tracked Energy" not in repr(result)
  assert result["entry_not_reportable"]["config_entry"][CONFIG_ACCOUNT_ID] == "**REDACTED**"
