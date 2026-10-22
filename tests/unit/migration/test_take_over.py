"""Taking the config entries over from the folder this integration used to live in.

The thing these tests exist to protect is an entity id. Every unique_id is a literal
`edf_energy_...` string, so an entity recreated under the new domain regenerates the id it
already had - but only if the old entity registry row has gone first, and that row only goes
when its config entry is removed. Get the order wrong and every entity comes back as
`sensor.edf_energy_..._2`, which breaks exactly the automations the whole move is designed
not to touch. Nothing about that is visible from the outside, so it is asserted here.
"""
import asyncio

import pytest

from custom_components.edfenergy_uk.const import DATA_MIGRATION, DOMAIN, PREDECESSOR_DOMAIN
from custom_components.edfenergy_uk.migration import (
  apply_device_customisations,
  apply_entity_customisations,
  async_take_over_old_entries,
  capture_devices,
  capture_entities,
  device_identifier_suffix,
)


class StubEntity:
  def __init__(self, platform, unique_id, entity_id, **kwargs):
    self.platform = platform
    self.unique_id = unique_id
    self.entity_id = entity_id
    self.name = kwargs.get("name")
    self.icon = kwargs.get("icon")
    self.area_id = kwargs.get("area_id")
    self.labels = kwargs.get("labels")
    self.hidden_by = kwargs.get("hidden_by")
    self.disabled_by = kwargs.get("disabled_by")


class StubEntityRegistry:
  def __init__(self, entities):
    self.entities = {e.entity_id: e for e in entities}
    self.updates = []
    self.fail_on = set()

  def async_update_entity(self, entity_id, **kwargs):
    if entity_id in self.fail_on:
      raise ValueError("registry said no")
    self.updates.append((entity_id, kwargs))


class StubDevice:
  def __init__(self, device_id, identifiers, **kwargs):
    self.id = device_id
    self.identifiers = identifiers
    self.area_id = kwargs.get("area_id")
    self.name_by_user = kwargs.get("name_by_user")
    self.labels = kwargs.get("labels")


class StubDeviceRegistry:
  def __init__(self, devices):
    self.devices = {d.id: d for d in devices}
    self.updates = []

  def async_update_device(self, device_id, **kwargs):
    self.updates.append((device_id, kwargs))


# ── device identifiers ───────────────────────────────────────────────────────

def test_the_suffix_is_the_half_that_is_not_the_domain():
  identifiers = {(PREDECESSOR_DOMAIN, "gas_sn_mprn")}

  assert device_identifier_suffix(identifiers, PREDECESSOR_DOMAIN) == "gas_sn_mprn"


def test_another_integrations_identifier_is_ignored():
  identifiers = {("some_other_integration", "gas_sn_mprn")}

  assert device_identifier_suffix(identifiers, PREDECESSOR_DOMAIN) is None


@pytest.mark.parametrize("identifiers", [None, set(), {("only-one-part",)}, {None}])
def test_a_malformed_identifier_is_not_an_error(identifiers):
  assert device_identifier_suffix(identifiers, PREDECESSOR_DOMAIN) is None


# ── capturing ────────────────────────────────────────────────────────────────

def test_only_the_old_platforms_entities_are_captured():
  registry = StubEntityRegistry([
    StubEntity(PREDECESSOR_DOMAIN, "edf_energy_a_balance", "sensor.edf_energy_a_balance"),
    StubEntity("some_other_integration", "other_1", "sensor.other_1"),
  ])

  captured = capture_entities(registry)

  assert list(captured) == ["edf_energy_a_balance"]


def test_what_the_user_changed_is_captured_with_the_entity_id():
  registry = StubEntityRegistry([
    StubEntity(PREDECESSOR_DOMAIN, "uid", "sensor.edf_energy_x", name="My name",
               icon="mdi:flash", area_id="kitchen", labels={"a"}, hidden_by="user"),
  ])

  captured = capture_entities(registry)["uid"]

  assert captured["entity_id"] == "sensor.edf_energy_x"
  assert captured["name"] == "My name"
  assert captured["icon"] == "mdi:flash"
  assert captured["area_id"] == "kitchen"
  assert captured["labels"] == {"a"}
  assert captured["hidden_by"] == "user"


def test_devices_are_captured_against_their_suffix():
  registry = StubDeviceRegistry([
    StubDevice("d1", {(PREDECESSOR_DOMAIN, "electricity_sn_mpan")}, area_id="hall",
               name_by_user="Meter"),
    StubDevice("d2", {("other", "thing")}, area_id="shed"),
  ])

  captured = capture_devices(registry)

  assert list(captured) == ["electricity_sn_mpan"]
  assert captured["electricity_sn_mpan"]["area_id"] == "hall"
  assert captured["electricity_sn_mpan"]["name_by_user"] == "Meter"


# ── putting things back ──────────────────────────────────────────────────────

def test_customisations_go_back_onto_the_new_entities():
  registry = StubEntityRegistry([StubEntity(DOMAIN, "uid", "sensor.edf_energy_x")])
  captured = {"uid": {"entity_id": "sensor.edf_energy_x", "name": "My name",
                      "icon": "mdi:flash", "area_id": "kitchen", "labels": None,
                      "hidden_by": None, "disabled_by": None}}

  restored, forced = apply_entity_customisations(registry, captured)

  assert restored == 1
  assert forced == []
  entity_id, updates = registry.updates[0]
  assert entity_id == "sensor.edf_energy_x"
  assert updates == {"name": "My name", "icon": "mdi:flash", "area_id": "kitchen"}


def test_an_entity_id_that_came_back_different_is_moved_back():
  # The failure this migration exists to prevent: something took the id and the entity
  # landed on a "_2" suffix.
  registry = StubEntityRegistry([StubEntity(DOMAIN, "uid", "sensor.edf_energy_x_2")])
  captured = {"uid": {"entity_id": "sensor.edf_energy_x", "name": None, "icon": None,
                      "area_id": None, "labels": None, "hidden_by": None, "disabled_by": None}}

  restored, forced = apply_entity_customisations(registry, captured)

  assert forced == ["sensor.edf_energy_x"]
  assert registry.updates[0][1]["new_entity_id"] == "sensor.edf_energy_x"
  assert restored == 1


def test_an_entity_nobody_captured_is_left_alone():
  registry = StubEntityRegistry([StubEntity(DOMAIN, "brand-new", "sensor.edf_energy_new")])

  restored, forced = apply_entity_customisations(registry, {})

  assert (restored, forced, registry.updates) == (0, [], [])


def test_one_entity_that_cannot_be_restored_does_not_abandon_the_rest():
  registry = StubEntityRegistry([
    StubEntity(DOMAIN, "bad", "sensor.edf_energy_bad"),
    StubEntity(DOMAIN, "good", "sensor.edf_energy_good"),
  ])
  registry.fail_on = {"sensor.edf_energy_bad"}
  captured = {
    uid: {"entity_id": f"sensor.edf_energy_{uid}", "name": "n", "icon": None,
          "area_id": None, "labels": None, "hidden_by": None, "disabled_by": None}
    for uid in ("bad", "good")
  }

  restored, _ = apply_entity_customisations(registry, captured)

  assert restored == 1
  assert [e for e, _ in registry.updates] == ["sensor.edf_energy_good"]


def test_device_area_and_name_go_back():
  registry = StubDeviceRegistry([StubDevice("d1", {(DOMAIN, "electricity_sn_mpan")})])
  captured = {"electricity_sn_mpan": {"area_id": "hall", "name_by_user": "Meter", "labels": None}}

  assert apply_device_customisations(registry, captured) == 1
  assert registry.updates[0] == ("d1", {"area_id": "hall", "name_by_user": "Meter"})


# ── the order of the hand-over ───────────────────────────────────────────────

class StubFlowManager:
  def __init__(self, log):
    self._log = log

  async def async_init(self, domain, context=None, data=None):
    self._log.append(("flow", domain, context.get("source"), data))


class StubOldEntry:
  def __init__(self, entry_id, title, data, options=None, unique_id=None):
    self.entry_id = entry_id
    self.title = title
    self.data = data
    self.options = options or {}
    self.unique_id = unique_id
    self.minor_version = 1


class StubConfigEntries:
  def __init__(self, entries, log):
    self._entries = entries
    self._log = log
    self.flow = StubFlowManager(log)

  def async_entries(self, domain):
    return [e for e in self._entries if domain == PREDECESSOR_DOMAIN]

  async def async_remove(self, entry_id):
    self._log.append(("remove", entry_id))


class StubHass:
  def __init__(self, entries, log):
    self.data = {}
    self.config_entries = StubConfigEntries(entries, log)
    self._log = log

  def async_create_task(self, coro):
    # The scheduling is logged, not just the flow that eventually runs. Logging only the
    # flow would make the ordering test vacuous: the removals are awaited inline, so a
    # scheduled flow always lands after them whichever order the code asks for.
    self._log.append(("schedule",))
    return asyncio.ensure_future(coro)


@pytest.fixture
def empty_registries(monkeypatch):
  monkeypatch.setattr("custom_components.edfenergy_uk.migration.er.async_get",
                      lambda hass: StubEntityRegistry([]))
  monkeypatch.setattr("custom_components.edfenergy_uk.migration.dr.async_get",
                      lambda hass: StubDeviceRegistry([]))


@pytest.mark.asyncio
async def test_nothing_happens_when_there_is_nothing_to_take_over(empty_registries):
  log = []
  hass = StubHass([], log)

  assert await async_take_over_old_entries(hass) == 0
  assert log == []
  assert DATA_MIGRATION not in (hass.data.get(DOMAIN) or {})


@pytest.mark.asyncio
async def test_the_old_entry_is_removed_before_the_new_one_is_created(empty_registries):
  """The invariant the whole migration rests on.

  Removing the old config entry is what releases its entity registry rows, and those rows
  hold the entity ids the new entities have to be given. Create first and every entity is
  handed a "_2" suffix instead - which is silent, and breaks every automation referring to
  the old id.
  """
  log = []
  hass = StubHass([StubOldEntry("old-1", "A-XXXXXX", {"kind": "account"})], log)

  assert await async_take_over_old_entries(hass) == 1
  await asyncio.sleep(0)

  kinds = [row[0] for row in log]
  assert kinds == ["remove", "schedule", "flow"], f"wrong order: {kinds}"


@pytest.mark.asyncio
async def test_every_entry_is_carried_across_with_its_data_and_options(empty_registries):
  log = []
  hass = StubHass([
    StubOldEntry("old-1", "A-XXXXXX", {"kind": "account"}, {"show_account_tab_beta": False}),
    StubOldEntry("old-2", "Tracker (cost tracker)", {"kind": "cost_tracker"},
                 unique_id="edf_energy_ct_A-XXXXXX_sensor.x"),
  ], log)

  assert await async_take_over_old_entries(hass) == 2
  await asyncio.sleep(0)

  # both removed before either is even queued for recreation
  assert [row[0] for row in log] == [
    "remove", "remove", "schedule", "schedule", "flow", "flow"
  ]
  flows = [row for row in log if row[0] == "flow"]
  assert all(domain == DOMAIN and source == "import" for _, domain, source, _ in flows)
  first = flows[0][3]
  assert first["data"] == {"kind": "account"}
  assert first["options"] == {"show_account_tab_beta": False}
  assert flows[1][3]["unique_id"] == "edf_energy_ct_A-XXXXXX_sensor.x"


@pytest.mark.asyncio
async def test_the_capture_is_stashed_before_anything_is_removed(monkeypatch):
  # It has to survive until the new entities exist, which is after this returns.
  monkeypatch.setattr(
    "custom_components.edfenergy_uk.migration.er.async_get",
    lambda hass: StubEntityRegistry([
      StubEntity(PREDECESSOR_DOMAIN, "uid", "sensor.edf_energy_x", area_id="kitchen")
    ]),
  )
  monkeypatch.setattr(
    "custom_components.edfenergy_uk.migration.dr.async_get",
    lambda hass: StubDeviceRegistry([StubDevice("d1", {(PREDECESSOR_DOMAIN, "gas_a_b")})]),
  )
  log = []
  hass = StubHass([StubOldEntry("old-1", "A-XXXXXX", {"kind": "account"})], log)

  await async_take_over_old_entries(hass)

  captured = hass.data[DOMAIN][DATA_MIGRATION]
  assert captured["entities"]["uid"]["entity_id"] == "sensor.edf_energy_x"
  assert captured["entities"]["uid"]["area_id"] == "kitchen"
  assert "gas_a_b" in captured["devices"]


