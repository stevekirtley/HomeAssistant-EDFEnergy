"""A config entry that lost its 'kind' used to break setup permanently.

Reported on Reddit against 19.2.4: `KeyError: 'kind'` from async_setup_entry, with the
integration showing "Failed to set up". The entry had an account id but no kind, and
nothing could put it right - the migration that fills the kind in only runs while the
entry is below the current config version, so an entry already at the current version
stayed broken through every restart. 19.2.4 did not cause it; updating merely forced the
reload that showed it.
"""
import pytest

from custom_components.edfenergy_uk import _infer_config_kind
from custom_components.edfenergy_uk.config.kind import get_config_kind
from custom_components.edfenergy_uk.const import (
  CONFIG_ACCOUNT_ID,
  CONFIG_COST_TRACKER_TARGET_ENTITY_ID,
  CONFIG_KIND_ACCOUNT,
  CONFIG_KIND_COST_TRACKER,
  CONFIG_KIND_TARIFF_COMPARISON,
  CONFIG_TARIFF_COMPARISON_PRODUCT_CODE,
)


def test_an_entry_with_only_an_account_id_is_an_account():
  """The reported case: the great majority of entries, and the safe default."""
  assert _infer_config_kind({CONFIG_ACCOUNT_ID: "A-XXXXXX"}) == CONFIG_KIND_ACCOUNT


def test_a_cost_tracker_is_not_mistaken_for_an_account():
  """Every kind carries the account id, so the child's own field is what tells them apart."""
  config = {CONFIG_ACCOUNT_ID: "A-XXXXXX", CONFIG_COST_TRACKER_TARGET_ENTITY_ID: "sensor.x"}

  assert _infer_config_kind(config) == CONFIG_KIND_COST_TRACKER


def test_a_tariff_comparison_is_not_mistaken_for_an_account():
  config = {CONFIG_ACCOUNT_ID: "A-XXXXXX", CONFIG_TARIFF_COMPARISON_PRODUCT_CODE: "GO-ELEC-12M"}

  assert _infer_config_kind(config) == CONFIG_KIND_TARIFF_COMPARISON


def test_an_empty_entry_still_resolves_rather_than_raising():
  """Setup must not fail here whatever the entry looks like."""
  assert _infer_config_kind({}) == CONFIG_KIND_ACCOUNT


def test_a_sibling_without_a_kind_does_not_bring_the_account_down():
  """Reported against 21.0.0 by two users after the hand-over from the old domain.

  `KeyError: 'kind'` from async_setup_entry, raised while the account entry walked its
  sibling entries to reload them. The account's own entry repairs a missing kind before it
  gets here, but the siblings were read by key, so one entry without a kind took the whole
  account down - no meters, no export, no free electricity, no EV device.

  The hand-over is what makes this reachable: it copies an old entry's data verbatim and
  recreates it at the current config version, so the migration that would have filled the
  kind in never runs on it.
  """
  siblings = [
    {CONFIG_ACCOUNT_ID: "A-XXXXXX", "kind": CONFIG_KIND_ACCOUNT},
    # The one that used to raise.
    {CONFIG_ACCOUNT_ID: "A-XXXXXX", CONFIG_COST_TRACKER_TARGET_ENTITY_ID: "sensor.x"},
    {CONFIG_ACCOUNT_ID: "A-OTHER", CONFIG_TARIFF_COMPARISON_PRODUCT_CODE: "GO-ELEC-12M"},
  ]

  reloaded = []
  for config in siblings:
    kind = config.get("kind") or _infer_config_kind(config)
    if kind != CONFIG_KIND_ACCOUNT and config.get(CONFIG_ACCOUNT_ID) == "A-XXXXXX":
      reloaded.append(config)

  # The kindless cost tracker is recognised and reloaded; the other account's entry is left
  # alone; nothing raises.
  assert reloaded == [siblings[1]]


def test_an_entry_missing_its_account_id_is_skipped_rather_than_raising():
  """The same line read the account id by key too, so it had the same failure available."""
  config = {CONFIG_COST_TRACKER_TARGET_ENTITY_ID: "sensor.x"}

  kind = config.get("kind") or _infer_config_kind(config)

  assert kind == CONFIG_KIND_COST_TRACKER
  assert config.get(CONFIG_ACCOUNT_ID) is None


def test_the_kind_is_inferred_through_the_shared_helper():
  """The platforms, the config flow and the discovery sweep all go through this."""
  assert get_config_kind({CONFIG_ACCOUNT_ID: "A-XXXXXX"}) == CONFIG_KIND_ACCOUNT
  assert get_config_kind({"kind": CONFIG_KIND_COST_TRACKER}) == CONFIG_KIND_COST_TRACKER
  assert get_config_kind({CONFIG_COST_TRACKER_TARGET_ENTITY_ID: "sensor.x"}) == CONFIG_KIND_COST_TRACKER
  assert get_config_kind({}) == CONFIG_KIND_ACCOUNT


@pytest.mark.asyncio
async def test_the_discovery_sweep_survives_an_entry_without_a_kind():
  """Reported on 21.0.1, every two hours: `KeyError: 'kind'` from discovery.py.

  21.0.1 stopped a kindless entry taking setup down, which is what let the discovery timer
  start running at all - and it walked the same entries, reading the kind by key. The
  exception landed in a timer task so the account kept working, but the sweep stopped at the
  bad entry, so no new energy entity was ever offered as a cost tracker.

  A disabled entry is why this does not clear itself: async_entries includes disabled
  entries, but a disabled entry is never set up, so it never repairs its own kind.
  """
  from homeassistant.helpers import entity_registry as er
  from homeassistant.helpers import discovery_flow

  from custom_components.edfenergy_uk import discovery as discovery_module
  from custom_components.edfenergy_uk.discovery import DiscoveryManager

  class FakeEntity:
    def __init__(self, entity_id, unique_id):
      self.entity_id = entity_id
      self.unique_id = unique_id
      self.disabled_by = None
      self.unit_of_measurement = "kWh"
      self.name = None
      self.original_name = "Some Meter"

  tracked = FakeEntity("sensor.already_tracked", "already_tracked")
  fresh = FakeEntity("sensor.brand_new", "brand_new")

  class FakeEntityRegistry:
    entities = {"sensor.already_tracked": tracked, "sensor.brand_new": fresh}

  class FakeEntry:
    def __init__(self, data):
      self.data = data

  entries = [
    # The kindless entry, listed first so a KeyError here stops everything after it.
    FakeEntry({CONFIG_ACCOUNT_ID: "A-XXXXXX", CONFIG_COST_TRACKER_TARGET_ENTITY_ID: "sensor.already_tracked"}),
    FakeEntry({CONFIG_ACCOUNT_ID: "A-XXXXXX", "kind": CONFIG_KIND_ACCOUNT}),
  ]

  class FakeConfigEntries:
    def async_entries(self, domain, include_ignore=False):
      return entries

  class FakeHass:
    config_entries = FakeConfigEntries()

  created = []

  original_registry = er.async_get
  original_create_flow = discovery_flow.async_create_flow
  er.async_get = lambda hass: FakeEntityRegistry()
  discovery_module.er.async_get = er.async_get
  discovery_module.discovery_flow.async_create_flow = (
    lambda hass, domain, context, data, discovery_key: created.append(data)
  )

  try:
    await DiscoveryManager(FakeHass(), "A-XXXXXX")._async_start_discovery()
  finally:
    er.async_get = original_registry
    discovery_module.er.async_get = original_registry
    discovery_module.discovery_flow.async_create_flow = original_create_flow

  # The kindless entry is recognised as the cost tracker it is, so the entity it already
  # tracks is not offered again, and the sweep carries on to find the new one.
  assert [data[CONFIG_COST_TRACKER_TARGET_ENTITY_ID] for data in created] == ["sensor.brand_new"]
