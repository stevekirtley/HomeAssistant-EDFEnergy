"""Telling our own old edf_energy apart from the other EDF integration that uses the domain.

Bobby5291/HomeAssistant-EDF-UK installs into custom_components/edf_energy under that same
domain. Everything this integration does to the old domain - deleting the folder, taking the
entries over, clearing repairs, registering actions - is only safe once the thing in front of
it is shown to be ours. These pin down what counts as shown.
"""
import pytest

from custom_components.edfenergy_uk.const import (
  CONFIG_ACCOUNT_ID,
  CONFIG_KIND,
  CONFIG_KIND_ACCOUNT,
  CONFIG_KIND_COST_TRACKER,
  DATA_PREDECESSOR_FOLDER,
  DOMAIN,
  PREDECESSOR_DOMAIN,
)
from custom_components.edfenergy_uk.predecessor import (
  FOLDER_NOT_OURS,
  FOLDER_OURS,
  accounts_shared_with_other_integration,
  is_our_old_entry,
  manifest_is_ours,
  old_domain_is_ours_or_gone,
)


class StubEntry:
  def __init__(self, data=None, version=9, source="user", disabled_by=None):
    self.data = data or {}
    self.version = version
    self.source = source
    self.disabled_by = disabled_by


class StubConfigEntries:
  def __init__(self, by_domain):
    self._by_domain = by_domain

  def async_entries(self, domain=None):
    return list(self._by_domain.get(domain, []))


class StubHass:
  def __init__(self, by_domain, folder=None):
    self.config_entries = StubConfigEntries(by_domain)
    self.data = {DOMAIN: {DATA_PREDECESSOR_FOLDER: folder}}


def ours(account_id="A-XXXXXX", kind=CONFIG_KIND_ACCOUNT):
  return StubEntry({CONFIG_KIND: kind, CONFIG_ACCOUNT_ID: account_id})


def theirs(account_id="A-XXXXXX"):
  # What the other integration's flow creates: version 1, credentials, no kind.
  return StubEntry({"email": "x@example.com", "password": "p", CONFIG_ACCOUNT_ID: account_id}, version=1)


# ── the manifest ─────────────────────────────────────────────────────────────

def test_a_manifest_from_one_of_our_releases_is_ours():
  assert manifest_is_ours({
    "domain": PREDECESSOR_DOMAIN,
    "codeowners": ["@stevekirtley"],
    "documentation": "https://github.com/stevekirtley/HomeAssistant-EDFEnergy",
  })


def test_the_other_integrations_manifest_is_not():
  assert not manifest_is_ours({
    "domain": PREDECESSOR_DOMAIN,
    "codeowners": ["@someone-else"],
    "documentation": "https://github.com/someone-else/ha-edf-energy",
  })


def test_our_owner_on_a_different_domain_is_not_the_old_folder():
  assert not manifest_is_ours({"domain": "something_else", "codeowners": ["@stevekirtley"]})


@pytest.mark.parametrize("manifest", [None, [], "edf_energy", {}])
def test_nonsense_is_not_ours(manifest):
  assert not manifest_is_ours(manifest)


# ── an entry ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("folder", [None, FOLDER_OURS, FOLDER_NOT_OURS])
def test_an_entry_with_our_kind_and_version_is_ours_wherever_it_is(folder):
  assert is_our_old_entry(ours(), folder)
  assert is_our_old_entry(ours(kind=CONFIG_KIND_COST_TRACKER), folder)


@pytest.mark.parametrize("folder", [None, FOLDER_OURS, FOLDER_NOT_OURS])
def test_the_other_integrations_entry_is_never_ours(folder):
  assert not is_our_old_entry(theirs(), folder)


def test_the_right_kind_at_the_wrong_version_is_not_ours():
  assert not is_our_old_entry(StubEntry({CONFIG_KIND: CONFIG_KIND_ACCOUNT}, version=1), FOLDER_OURS)


def test_a_kind_we_never_had_is_not_ours():
  assert not is_our_old_entry(StubEntry({CONFIG_KIND: "something"}), FOLDER_OURS)


def test_an_ignored_suggestion_of_ours_is_ours():
  # Ignored entries have no data at all, so no kind - the version is what shows it.
  assert is_our_old_entry(StubEntry({}, source="ignore"), None)
  assert not is_our_old_entry(StubEntry({}, version=1, source="ignore"), None)


def test_an_entry_without_a_kind_needs_our_folder_as_well():
  entry = StubEntry({CONFIG_ACCOUNT_ID: "A-XXXXXX"})

  assert is_our_old_entry(entry, FOLDER_OURS)
  assert not is_our_old_entry(entry, None)
  assert not is_our_old_entry(entry, FOLDER_NOT_OURS)


# ── the domain as a whole ────────────────────────────────────────────────────

def test_the_old_domain_is_ours_when_only_we_have_been_there():
  hass = StubHass({PREDECESSOR_DOMAIN: [ours()]})

  assert old_domain_is_ours_or_gone(hass, FOLDER_OURS)
  assert old_domain_is_ours_or_gone(hass, None)


def test_the_other_integrations_folder_means_it_is_not():
  assert not old_domain_is_ours_or_gone(StubHass({}), FOLDER_NOT_OURS)


def test_the_other_integrations_entry_means_it_is_not():
  assert not old_domain_is_ours_or_gone(StubHass({PREDECESSOR_DOMAIN: [theirs()]}), None)


def test_entries_of_theirs_that_do_nothing_do_not_count():
  hass = StubHass({PREDECESSOR_DOMAIN: [
    StubEntry({}, version=1, source="ignore"),
    StubEntry({CONFIG_ACCOUNT_ID: "A-XXXXXX"}, version=1, disabled_by="user"),
  ]})

  assert old_domain_is_ours_or_gone(hass, None)


# ── a shared account ─────────────────────────────────────────────────────────

def test_an_account_both_have_set_up_is_shared():
  hass = StubHass({DOMAIN: [ours("A-XXXXXX")], PREDECESSOR_DOMAIN: [theirs("a-xxxxxx")]})

  assert accounts_shared_with_other_integration(hass) == {"A-XXXXXX"}


def test_different_accounts_are_not_shared():
  hass = StubHass({DOMAIN: [ours("A-XXXXXX")], PREDECESSOR_DOMAIN: [theirs("A-YYYYYY")]})

  assert accounts_shared_with_other_integration(hass) == set()


def test_our_own_leftover_entry_is_not_another_integration():
  # Between an update and the hand-over our old entry is still on the old domain.
  hass = StubHass({DOMAIN: [ours("A-XXXXXX")], PREDECESSOR_DOMAIN: [ours("A-XXXXXX")]})

  assert accounts_shared_with_other_integration(hass) == set()


def test_only_our_accounts_count_on_our_side():
  hass = StubHass({
    DOMAIN: [ours("A-XXXXXX", kind=CONFIG_KIND_COST_TRACKER)],
    PREDECESSOR_DOMAIN: [theirs("A-XXXXXX")],
  })

  assert accounts_shared_with_other_integration(hass) == set()
