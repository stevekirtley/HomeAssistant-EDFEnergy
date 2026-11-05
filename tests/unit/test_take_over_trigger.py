"""Adding the integration is what starts the hand-over.

This is the load-bearing piece of the whole move, and the reason it exists is a mistake
worth recording. The first design did the hand-over in async_setup, on the assumption that
Home Assistant would run this integration once it was on disk. It does not. bootstrap only
sets up domains that are named in configuration.yaml, listed as a default integration, or
already hold a config entry - and immediately after an update this one holds none, because
every entry still belongs to the domain it is replacing. So async_setup never ran, the
entries sat on a domain with no code behind it, and the account went dark.

Nothing can change that from inside the integration. The only thing that refers to a domain
with no entries is a user adding it from Settings, so that is where the hand-over lives.
"""
import json

import pytest

from custom_components.edfenergy_uk.config_flow import EDFEnergyConfigFlow
from custom_components.edfenergy_uk.const import (
  CONFIG_ACCOUNT_ID,
  CONFIG_KIND,
  CONFIG_KIND_ACCOUNT,
  DOMAIN,
  PREDECESSOR_DOMAIN,
)


class StubEntry:
  def __init__(self, account_id, kind=CONFIG_KIND_ACCOUNT, version=9):
    self.data = {CONFIG_ACCOUNT_ID: account_id}
    if kind is not None:
      self.data[CONFIG_KIND] = kind
    self.version = version
    self.source = "user"
    self.disabled_by = None
    self.options = {}
    self.title = f"EDF Energy ({account_id})"
    self.unique_id = account_id
    self.entry_id = f"entry-{account_id}-{kind}"


class StubConfigEntries:
  def __init__(self, by_domain):
    self._by_domain = by_domain

  def async_entries(self, domain=None, include_ignore=True, include_disabled=True):
    # Home Assistant's own _async_current_entries passes include_ignore, so the stub has
    # to take it even though nothing here sets it.
    return list(self._by_domain.get(domain, []))


class StubConfig:
  def __init__(self, config_dir):
    self.config_dir = str(config_dir)


class StubHass:
  def __init__(self, by_domain, config_dir):
    self.config_entries = StubConfigEntries(by_domain)
    self.config = StubConfig(config_dir)
    self.data = {}

  async def async_add_executor_job(self, func, *args):
    return func(*args)


def _flow(by_domain, config_dir="/nonexistent-config"):
  flow = EDFEnergyConfigFlow()
  flow.hass = StubHass(by_domain, config_dir)
  return flow


def _our_old_folder(tmp_path):
  folder = tmp_path / "custom_components" / PREDECESSOR_DOMAIN
  folder.mkdir(parents=True)
  (folder / "manifest.json").write_text(json.dumps({
    "domain": PREDECESSOR_DOMAIN, "version": "19.2.4", "codeowners": ["@stevekirtley"],
  }))
  return tmp_path


# ── when there is something to take over ─────────────────────────────────────

@pytest.mark.asyncio
async def test_old_entries_are_found(tmp_path):
  flow = _flow({PREDECESSOR_DOMAIN: [StubEntry("a-1")]})

  _, entries = await flow._async_entries_to_take_over()

  assert len(entries) == 1


@pytest.mark.asyncio
async def test_entries_on_this_domain_are_not_mistaken_for_old_ones():
  # A second account being added to a working install must not look like a migration.
  flow = _flow({DOMAIN: [StubEntry("a-1")]})

  assert (await flow._async_entries_to_take_over())[1] == []


@pytest.mark.asyncio
async def test_the_other_edf_integrations_entries_are_not_offered(monkeypatch):
  """Same domain, different integration: its flow is at version 1 and records no kind.

  Taking these over would remove them, with their entities and devices, and import their
  data, password included, into entries this integration cannot set up.
  """
  # Arrange
  flow = _flow({PREDECESSOR_DOMAIN: [StubEntry("a-1", kind=None, version=1)]})
  monkeypatch.setattr(
    EDFEnergyConfigFlow, "async_show_form",
    lambda self, **kwargs: {"type": "form", **kwargs},
  )

  # Act
  result = await flow.async_step_user(None)

  # Assert - an ordinary setup, as if the other integration were not there
  assert result["step_id"] == "account"


@pytest.mark.asyncio
async def test_an_entry_without_a_kind_is_only_ours_when_the_folder_is(tmp_path):
  entries = {PREDECESSOR_DOMAIN: [StubEntry("a-1", kind=None)]}

  assert (await _flow(entries)._async_entries_to_take_over())[1] == []
  assert len((await _flow(entries, _our_old_folder(tmp_path))._async_entries_to_take_over())[1]) == 1


@pytest.mark.asyncio
async def test_adding_the_integration_offers_the_take_over_first(monkeypatch):
  # Arrange
  flow = _flow({PREDECESSOR_DOMAIN: [StubEntry("a-1")]})
  shown = {}
  monkeypatch.setattr(
    EDFEnergyConfigFlow, "async_show_form",
    lambda self, **kwargs: shown.update(kwargs) or {"type": "form", **kwargs},
  )

  # Act - the user pressing Add integration
  result = await flow.async_step_user(None)

  # Assert
  assert result["step_id"] == "take_over"
  assert shown["description_placeholders"]["accounts"] == "A-1"
  assert shown["description_placeholders"]["count"] == "1"


@pytest.mark.asyncio
async def test_every_old_account_is_named_on_the_form(monkeypatch):
  flow = _flow({PREDECESSOR_DOMAIN: [
    StubEntry("a-2"), StubEntry("a-1"), StubEntry("a-1", kind="cost_tracker"),
  ]})
  shown = {}
  monkeypatch.setattr(
    EDFEnergyConfigFlow, "async_show_form",
    lambda self, **kwargs: shown.update(kwargs) or {"type": "form", **kwargs},
  )

  await flow.async_step_take_over(None)

  # Listed once each and in a predictable order, not once per config entry.
  assert shown["description_placeholders"]["accounts"] == "A-1, A-2"
  assert shown["description_placeholders"]["count"] == "3"


@pytest.mark.asyncio
async def test_submitting_runs_the_hand_over(monkeypatch):
  # Arrange
  flow = _flow({PREDECESSOR_DOMAIN: [StubEntry("a-1")]})
  called = []

  async def fake_take_over(hass, folder):
    called.append(hass)
    return 1

  monkeypatch.setattr("custom_components.edfenergy_uk.config_flow.async_take_over_old_entries", fake_take_over)
  monkeypatch.setattr(
    EDFEnergyConfigFlow, "async_abort",
    lambda self, **kwargs: {"type": "abort", **kwargs},
  )

  # Act
  result = await flow.async_step_take_over({})

  # Assert
  assert called == [flow.hass]
  assert result["reason"] == "taken_over"
  assert result["description_placeholders"]["old_domain"] == PREDECESSOR_DOMAIN


# ── when there is not ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_a_fresh_install_is_never_asked_about_a_take_over(monkeypatch):
  """A new user has nothing to adopt and must not be asked about one."""
  # Arrange
  flow = _flow({})
  monkeypatch.setattr(
    EDFEnergyConfigFlow, "async_show_form",
    lambda self, **kwargs: {"type": "form", **kwargs},
  )

  # Act
  result = await flow.async_step_user(None)

  # Assert - straight to the ordinary account form.
  assert result["step_id"] == "account"


@pytest.mark.asyncio
async def test_the_take_over_step_falls_through_if_the_entries_vanish(monkeypatch):
  # Two people adding the integration at once, or the form left open while the other
  # flow finished. Nothing to adopt is an ordinary setup, not an error.
  flow = _flow({})
  monkeypatch.setattr(
    EDFEnergyConfigFlow, "async_show_form",
    lambda self, **kwargs: {"type": "form", **kwargs},
  )

  result = await flow.async_step_take_over(None)

  assert result["step_id"] == "account"


@pytest.mark.asyncio
async def test_the_hand_over_is_not_run_when_there_is_nothing_to_hand_over(monkeypatch):
  flow = _flow({})
  called = []
  monkeypatch.setattr(
    "custom_components.edfenergy_uk.config_flow.async_take_over_old_entries",
    lambda hass, folder: called.append(hass),
  )
  monkeypatch.setattr(
    EDFEnergyConfigFlow, "async_show_form",
    lambda self, **kwargs: {"type": "form", **kwargs},
  )

  await flow.async_step_take_over({})

  assert called == []
