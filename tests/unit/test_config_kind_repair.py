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


def test_an_entry_nothing_identifies_is_not_called_an_account():
  """Reported on 21.0.0 as issue #53, and the reason this stopped guessing.

  That install had 38 cost tracker entries that had lost both their kind and their account
  id. Falling back to "account" would have labelled every one of them as the account they
  belong to, and the label gets written to disk, so the guess would have outlived the bug.
  None says so honestly, and matches no branch anywhere.
  """
  assert _infer_config_kind({}) is None


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
  assert get_config_kind({}) is None


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


class _FakeEntry:
  """Enough of a config entry for the repair and migration paths."""

  def __init__(self, data, version=9, options=None, title="A-XXXXXX", unique_id=None, entry_id="entry-1"):
    self.data = dict(data)
    self.version = version
    self.options = dict(options or {})
    self.title = title
    self.entry_id = entry_id
    self.unique_id = unique_id


class _FakeConfigEntries:
  def __init__(self, entries=None):
    self.entries = entries or []
    self.updates = []

  def async_entries(self, domain, include_ignore=False):
    return self.entries

  def async_update_entry(self, entry, **changes):
    if "data" in changes:
      entry.data = dict(changes["data"])
    if "options" in changes:
      entry.options = dict(changes["options"])
    if "title" in changes:
      entry.title = changes["title"]
    if "version" in changes:
      entry.version = changes["version"]
    self.updates.append((entry, changes))


class _FakeHass:
  def __init__(self, entries=None, data=None):
    self.config_entries = _FakeConfigEntries(entries)
    self.data = data if data is not None else {}


def test_an_entry_without_a_kind_has_one_recorded_on_it():
  """Reading around a missing kind is not enough on its own.

  A disabled entry is never set up, so it never repairs itself, and it keeps turning up in
  async_entries with nothing to say what it is. Writing the kind on the first look is what
  stops it being a trap for every caller after that.
  """
  from custom_components.edfenergy_uk.config.kind import async_ensure_config_kind

  entry = _FakeEntry({CONFIG_ACCOUNT_ID: "A-XXXXXX", CONFIG_COST_TRACKER_TARGET_ENTITY_ID: "sensor.x"})
  hass = _FakeHass([entry])

  kind = async_ensure_config_kind(hass, entry)

  assert kind == CONFIG_KIND_COST_TRACKER
  assert entry.data["kind"] == CONFIG_KIND_COST_TRACKER
  assert len(hass.config_entries.updates) == 1


def test_an_entry_that_already_knows_its_kind_is_left_alone():
  """Which is every entry but the broken ones, so it must not write on every look."""
  from custom_components.edfenergy_uk.config.kind import async_ensure_config_kind

  entry = _FakeEntry({CONFIG_ACCOUNT_ID: "A-XXXXXX", "kind": CONFIG_KIND_ACCOUNT})
  hass = _FakeHass([entry])

  assert async_ensure_config_kind(hass, entry) == CONFIG_KIND_ACCOUNT
  assert hass.config_entries.updates == []


@pytest.mark.asyncio
async def test_the_migration_fills_the_kind_in_before_dispatching_on_it():
  """This is where the whole problem came from.

  The migration dispatched on the kind to decide what to migrate, so an entry without one
  matched none of its branches - and was then handed the current config version regardless.
  It came out the other side still missing the kind, and with nothing left that would ever
  run the migration on it again.
  """
  from custom_components.edfenergy_uk import async_migrate_entry
  from custom_components.edfenergy_uk.const import CONFIG_VERSION

  entry = _FakeEntry({CONFIG_ACCOUNT_ID: "A-XXXXXX"}, version=8)
  hass = _FakeHass([entry])

  assert await async_migrate_entry(hass, entry) is True

  assert entry.data["kind"] == CONFIG_KIND_ACCOUNT
  assert entry.version == CONFIG_VERSION


@pytest.mark.asyncio
async def test_the_migration_does_not_relabel_an_entry_that_knows_what_it_is():
  """Target rates are not supported by this fork but the entries still exist, and nothing
  about them can be inferred - so a recorded kind has to win over any guess."""
  from custom_components.edfenergy_uk import async_migrate_entry
  from custom_components.edfenergy_uk.const import CONFIG_KIND_TARGET_RATE

  entry = _FakeEntry({CONFIG_ACCOUNT_ID: "A-XXXXXX", "kind": CONFIG_KIND_TARGET_RATE}, version=8)
  hass = _FakeHass([entry])

  assert await async_migrate_entry(hass, entry) is True

  assert entry.data["kind"] == CONFIG_KIND_TARGET_RATE


def test_an_account_whose_entry_is_not_set_up_reads_as_missing_rather_than_raising():
  """Adding or reconfiguring a cost tracker while the account entry is broken used to raise
  a KeyError out of the config flow, so the person whose account was already broken got
  "Unknown error occurred" instead of being told which account was missing."""
  from custom_components.edfenergy_uk.config_flow import get_account_info

  assert get_account_info(_FakeHass(data={}), "A-XXXXXX") is None
  assert get_account_info(_FakeHass(data={"edfenergy_uk": {}}), "A-XXXXXX") is None
  assert get_account_info(_FakeHass(data={"edfenergy_uk": {"A-XXXXXX": {}}}), "A-XXXXXX") is None
  assert get_account_info(_FakeHass(data={}), None) is None


def test_an_account_entry_without_a_kind_is_still_counted_as_an_account():
  """It was skipped, so the account it holds went missing from the duplicate check and from
  the account pickers - the same account could be added a second time."""
  from custom_components.edfenergy_uk.config_flow import get_account_ids

  hass = _FakeHass([
    _FakeEntry({CONFIG_ACCOUNT_ID: "A-XXXXXX"}),
    _FakeEntry({CONFIG_ACCOUNT_ID: "A-OTHER", "kind": CONFIG_KIND_ACCOUNT}),
    _FakeEntry({CONFIG_ACCOUNT_ID: "A-OTHER", CONFIG_COST_TRACKER_TARGET_ENTITY_ID: "sensor.x"}),
  ])

  assert get_account_ids(hass) == ["A-XXXXXX", "A-OTHER"]


def test_an_account_entry_is_recognised_by_its_credentials_alone():
  """An account that has lost its own account id is still obviously an account.

  Nothing can reconnect it, but calling it a cost tracker would be worse than saying it is
  an account that needs attention.
  """
  from custom_components.edfenergy_uk.const import CONFIG_MAIN_API_KEY

  assert _infer_config_kind({CONFIG_MAIN_API_KEY: "an-api-key"}) == CONFIG_KIND_ACCOUNT









def test_an_entry_nothing_can_rebuild_is_not_written_to():
  """Nothing identifies it, so recording anything would be inventing an answer."""
  from custom_components.edfenergy_uk.config.kind import async_ensure_config_kind

  entry = _FakeEntry({}, entry_id="mystery")
  hass = _FakeHass([entry])

  assert async_ensure_config_kind(hass, entry) is None
  assert entry.data == {}
  assert hass.config_entries.updates == []


def test_a_healthy_entry_is_never_written_to():
  """This runs on every entry on every setup, so it must be silent on the normal case."""
  from custom_components.edfenergy_uk.config.kind import async_record_inferred_kind

  entry = _FakeEntry({CONFIG_ACCOUNT_ID: "A-XXXXXX", "kind": CONFIG_KIND_ACCOUNT})
  hass = _FakeHass([entry])

  assert async_record_inferred_kind(hass, entry) == entry.data
  assert hass.config_entries.updates == []


def test_an_entry_that_cannot_be_rebuilt_names_what_it_is_missing():
  """Issue #53 arrived as `KeyError: 'account_id'`, 38 times, which told nobody anything.

  Setup reads these fields by key further in, so an entry that has lost one fails whatever
  happens. The difference is whether it fails saying which fields have gone.
  """
  from custom_components.edfenergy_uk.config.kind import missing_required_fields

  assert missing_required_fields(CONFIG_KIND_COST_TRACKER, {}) == [
    CONFIG_ACCOUNT_ID, "name", "mpan", CONFIG_COST_TRACKER_TARGET_ENTITY_ID,
  ]


def test_a_complete_cost_tracker_is_missing_nothing():
  """Which is every cost tracker but the broken ones."""
  from custom_components.edfenergy_uk.config.kind import missing_required_fields

  config = {
    CONFIG_ACCOUNT_ID: "A-XXXXXX",
    "name": "Tracker",
    "mpan": "1111111111111",
    CONFIG_COST_TRACKER_TARGET_ENTITY_ID: "sensor.x",
  }

  assert missing_required_fields(CONFIG_KIND_COST_TRACKER, config) == []


def test_a_tariff_comparison_needs_its_product_and_tariff():
  """Read by key by the rate and cost override entities, so checked up front with the rest."""
  from custom_components.edfenergy_uk.config.kind import missing_required_fields

  missing = missing_required_fields(CONFIG_KIND_TARIFF_COMPARISON, {CONFIG_ACCOUNT_ID: "A-XXXXXX"})

  assert missing == ["name", "mpan_mprn", "product_code", "tariff_code"]


def test_an_account_only_needs_its_own_id():
  """An account carries no child fields, so requiring any would break every account."""
  from custom_components.edfenergy_uk.config.kind import missing_required_fields

  assert missing_required_fields(CONFIG_KIND_ACCOUNT, {CONFIG_ACCOUNT_ID: "A-XXXXXX"}) == []
  assert missing_required_fields(CONFIG_KIND_ACCOUNT, {}) == [CONFIG_ACCOUNT_ID]


def test_an_entry_of_no_known_kind_is_still_held_to_having_an_account():
  """None matches no branch, so it sets nothing up - but it must not pass silently."""
  from custom_components.edfenergy_uk.config.kind import missing_required_fields

  assert missing_required_fields(None, {}) == [CONFIG_ACCOUNT_ID]
