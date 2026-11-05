"""Running alongside the other EDF integration on the same account.

Both write `edf_energy:` external statistics with the same ids for the same meters, and the
recorder cannot rename an external statistic, so neither side can move. On a shared account
this one stops writing them rather than overwrite the other's Energy dashboard history. The
account cache had the same clash and has moved to a key of its own.
"""
from datetime import datetime, timezone

import pytest

from custom_components.edfenergy_uk.const import (
  CONFIG_ACCOUNT_ID,
  CONFIG_KIND,
  CONFIG_KIND_ACCOUNT,
  DATA_PREDECESSOR_FOLDER,
  DOMAIN,
  PREDECESSOR_DOMAIN,
)
from custom_components.edfenergy_uk.statistics import consumption, cost
from custom_components.edfenergy_uk.storage import account as account_store


class StubEntry:
  def __init__(self, data, version):
    self.data = data
    self.version = version
    self.source = "user"
    self.disabled_by = None


class StubConfigEntries:
  def __init__(self, by_domain):
    self._by_domain = by_domain

  def async_entries(self, domain=None):
    return list(self._by_domain.get(domain, []))


class StubHass:
  def __init__(self, their_account=None):
    by_domain = {DOMAIN: [StubEntry({CONFIG_KIND: CONFIG_KIND_ACCOUNT, CONFIG_ACCOUNT_ID: "A-XXXXXX"}, 9)]}
    if their_account:
      by_domain[PREDECESSOR_DOMAIN] = [StubEntry({CONFIG_ACCOUNT_ID: their_account, "password": "p"}, 1)]
    self.config_entries = StubConfigEntries(by_domain)
    self.data = {DOMAIN: {DATA_PREDECESSOR_FOLDER: None}}


NOW = datetime(2026, 11, 5, tzinfo=timezone.utc)
CONSUMPTION = [{"start": NOW, "end": NOW, "consumption": 1}]
RATES = [{"start": NOW, "end": NOW, "value_inc_vat": 0.2}]


class WentPast(Exception):
  pass


def _refuse_to_read(monkeypatch, module):
  async def last_sum(*args, **kwargs):
    raise WentPast()
  monkeypatch.setattr(module, "async_get_last_sum", last_sum)
  written = []
  monkeypatch.setattr(module, "async_add_external_statistics", lambda *args: written.append(args))
  return written


@pytest.mark.asyncio
@pytest.mark.parametrize("module, function", [
  (consumption, consumption.async_import_external_statistics_from_consumption),
  (cost, cost.async_import_external_statistics_from_cost),
])
async def test_on_a_shared_account_the_statistics_are_not_written(monkeypatch, module, function):
  written = _refuse_to_read(monkeypatch, module)

  result = await function(NOW, StubHass("a-xxxxxx"), "electricity_sn_mpan_previous_accumulative_consumption",
                          "name", CONSUMPTION, RATES, "kWh", "consumption")

  assert result is None
  assert written == []


@pytest.mark.asyncio
@pytest.mark.parametrize("module, function", [
  (consumption, consumption.async_import_external_statistics_from_consumption),
  (cost, cost.async_import_external_statistics_from_cost),
])
async def test_on_another_account_they_are(monkeypatch, module, function):
  _refuse_to_read(monkeypatch, module)

  # Getting as far as reading the last sum is far enough to show it carried on.
  with pytest.raises(WentPast):
    await function(NOW, StubHass("A-YYYYYY"), "electricity_sn_mpan_previous_accumulative_consumption",
                   "name", CONSUMPTION, RATES, "kWh", "consumption")


# ── the account cache ────────────────────────────────────────────────────────

@pytest.fixture
def stores(monkeypatch):
  contents = {}

  class StubStore:
    def __init__(self, hass, version, key):
      self.key = key

    async def async_load(self):
      return contents.get(self.key)

    async def async_save(self, data):
      contents[self.key] = data

  monkeypatch.setattr(account_store.storage, "Store", StubStore)
  return contents


@pytest.mark.asyncio
async def test_the_account_is_saved_under_this_domain(stores):
  await account_store.async_save_cached_account(StubHass(), "A-XXXXXX", {"id": "A-XXXXXX"})

  assert list(stores) == [f"{DOMAIN}.A-XXXXXX_account"]


@pytest.mark.asyncio
async def test_an_update_starts_from_the_old_cache(stores):
  stores[f"{PREDECESSOR_DOMAIN}.A-XXXXXX_account"] = {"id": "old"}

  assert await account_store.async_load_cached_account(StubHass(), "A-XXXXXX") == {"id": "old"}


@pytest.mark.asyncio
async def test_the_new_cache_wins_over_the_old(stores):
  stores[f"{PREDECESSOR_DOMAIN}.A-XXXXXX_account"] = {"id": "old"}
  stores[f"{DOMAIN}.A-XXXXXX_account"] = {"id": "new"}

  assert await account_store.async_load_cached_account(StubHass(), "A-XXXXXX") == {"id": "new"}


@pytest.mark.asyncio
async def test_the_old_cache_is_not_read_when_the_other_integration_could_have_written_it(stores):
  stores[f"{PREDECESSOR_DOMAIN}.A-XXXXXX_account"] = {"something": "of theirs"}

  assert await account_store.async_load_cached_account(StubHass("A-XXXXXX"), "A-XXXXXX") is None


# ── saying so ────────────────────────────────────────────────────────────────

def _capture_issues(monkeypatch):
  created, deleted = [], []
  monkeypatch.setattr("custom_components.edfenergy_uk.ir.async_create_issue",
                      lambda hass, domain, issue_id, **kwargs: created.append((issue_id, kwargs)))
  monkeypatch.setattr("custom_components.edfenergy_uk.ir.async_delete_issue",
                      lambda hass, domain, issue_id: deleted.append(issue_id))
  return created, deleted


def test_a_repair_names_the_shared_account(monkeypatch):
  from custom_components.edfenergy_uk import _async_update_shared_account_repair
  created, _ = _capture_issues(monkeypatch)

  _async_update_shared_account_repair(StubHass("a-xxxxxx"))

  assert [issue_id for issue_id, _ in created] == ["shared_with_other_integration"]
  assert created[0][1]["translation_placeholders"]["accounts"] == "A-XXXXXX"
  assert created[0][1]["is_fixable"] is False


def test_the_repair_goes_once_the_account_is_not_shared(monkeypatch):
  from custom_components.edfenergy_uk import _async_update_shared_account_repair
  created, deleted = _capture_issues(monkeypatch)

  _async_update_shared_account_repair(StubHass())

  assert created == []
  assert deleted == ["shared_with_other_integration"]
