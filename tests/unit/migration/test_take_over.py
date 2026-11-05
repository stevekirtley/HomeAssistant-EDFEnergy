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
  clear_old_notices,
  device_identifier_suffix,
)
from custom_components.edfenergy_uk.predecessor import FOLDER_NOT_OURS, FOLDER_OURS


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
    self.config_entry_id = kwargs.get("config_entry_id")


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
    self.config_entries = kwargs.get("config_entries", set())


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
  def __init__(self, entry_id, title, data, options=None, unique_id=None, source="user", version=9):
    self.entry_id = entry_id
    self.version = version
    self.disabled_by = None
    self.title = title
    self.data = data
    self.options = options or {}
    self.unique_id = unique_id
    self.minor_version = 1
    self.source = source


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


class StubIssueRegistry:
  def __init__(self, keys):
    self.issues = {key: object() for key in keys}


def _issue_registry(monkeypatch, keys):
  """Patch in an issue registry and record what gets deleted."""
  deleted = []
  monkeypatch.setattr("custom_components.edfenergy_uk.migration.ir.async_get",
                      lambda hass: StubIssueRegistry(keys))
  monkeypatch.setattr("custom_components.edfenergy_uk.migration.ir.async_delete_issue",
                      lambda hass, domain, issue_id: deleted.append((domain, issue_id)))
  return deleted


@pytest.fixture
def empty_registries(monkeypatch):
  monkeypatch.setattr("custom_components.edfenergy_uk.migration.er.async_get",
                      lambda hass: StubEntityRegistry([]))
  monkeypatch.setattr("custom_components.edfenergy_uk.migration.dr.async_get",
                      lambda hass: StubDeviceRegistry([]))
  monkeypatch.setattr("custom_components.edfenergy_uk.migration.ir.async_get",
                      lambda hass: StubIssueRegistry([]))
  monkeypatch.setattr("custom_components.edfenergy_uk.migration.ir.async_delete_issue",
                      lambda hass, domain, issue_id: None)


@pytest.mark.asyncio
async def test_nothing_happens_when_there_is_nothing_to_take_over(empty_registries):
  log = []
  hass = StubHass([], log)

  assert await async_take_over_old_entries(hass, FOLDER_OURS) == 0
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

  assert await async_take_over_old_entries(hass, FOLDER_OURS) == 1
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

  assert await async_take_over_old_entries(hass, FOLDER_OURS) == 2
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
      StubEntity(PREDECESSOR_DOMAIN, "uid", "sensor.edf_energy_x", area_id="kitchen",
                 config_entry_id="old-1")
    ]),
  )
  monkeypatch.setattr(
    "custom_components.edfenergy_uk.migration.dr.async_get",
    lambda hass: StubDeviceRegistry([StubDevice("d1", {(PREDECESSOR_DOMAIN, "gas_a_b")},
                                                config_entries={"old-1"})]),
  )
  _issue_registry(monkeypatch, [])
  log = []
  hass = StubHass([StubOldEntry("old-1", "A-XXXXXX", {"kind": "account"})], log)

  await async_take_over_old_entries(hass, FOLDER_OURS)

  captured = hass.data[DOMAIN][DATA_MIGRATION]
  assert captured["entities"]["uid"]["entity_id"] == "sensor.edf_energy_x"
  assert captured["entities"]["uid"]["area_id"] == "kitchen"
  assert "gas_a_b" in captured["devices"]




# ── notices the old domain left behind ──────────────────────────────────

def test_the_old_domains_notices_are_cleared(monkeypatch):
  # Nothing removes a notice when the folder that raised it goes, so after the hand-over
  # the 20.1.0 "stood down, waiting to be taken over" notice is still on screen saying
  # the opposite of what happened.
  deleted = _issue_registry(monkeypatch, [
    (PREDECESSOR_DOMAIN, "superseded_by_edfenergy_uk"),
    (PREDECESSOR_DOMAIN, "new_folder"),
  ])

  assert clear_old_notices(StubHass([], []), FOLDER_OURS) == 2
  assert sorted(deleted) == [
    (PREDECESSOR_DOMAIN, "new_folder"),
    (PREDECESSOR_DOMAIN, "superseded_by_edfenergy_uk"),
  ]


def test_nobody_elses_notices_are_touched(monkeypatch):
  deleted = _issue_registry(monkeypatch, [
    (PREDECESSOR_DOMAIN, "superseded_by_edfenergy_uk"),
    (DOMAIN, "api_key_needed"),
    ("homeassistant", "config_entry_reauth_edf_energy_abc"),
    ("recorder", "something_else"),
  ])

  assert clear_old_notices(StubHass([], []), FOLDER_OURS) == 1
  assert deleted == [(PREDECESSOR_DOMAIN, "superseded_by_edfenergy_uk")]


def test_no_notices_is_not_an_error(monkeypatch):
  deleted = _issue_registry(monkeypatch, [])

  assert clear_old_notices(StubHass([], []), FOLDER_OURS) == 0
  assert deleted == []


@pytest.mark.asyncio
async def test_the_hand_over_clears_them(monkeypatch):
  monkeypatch.setattr("custom_components.edfenergy_uk.migration.er.async_get",
                      lambda hass: StubEntityRegistry([]))
  monkeypatch.setattr("custom_components.edfenergy_uk.migration.dr.async_get",
                      lambda hass: StubDeviceRegistry([]))
  deleted = _issue_registry(monkeypatch, [(PREDECESSOR_DOMAIN, "superseded_by_edfenergy_uk")])

  log = []
  hass = StubHass([StubOldEntry("old-1", "A-XXXXXX", {"kind": "account"})], log)
  assert await async_take_over_old_entries(hass, FOLDER_OURS) == 1
  await asyncio.sleep(0)

  assert deleted == [(PREDECESSOR_DOMAIN, "superseded_by_edfenergy_uk")]


@pytest.mark.asyncio
async def test_every_field_survives_a_hand_over_of_an_account_and_its_children(empty_registries):
  """Issue #53, which is why this looks at the data rather than the ordering.

  That install came through this hand-over and ended up with 38 cost tracker entries that
  had lost both their kind and their account id, which left every one of them failing to set
  up and took the account down with them. The hand-over fires one flow per old entry, all at
  once, so if anything here could drop or cross-contaminate a payload this is where it would
  happen. Nothing does: every payload is asserted to match its own source exactly.

  A pass does not prove the install was fine, it rules this out as the place the fields went.
  """
  log = []
  old_entries = [
    StubOldEntry("account", "A-XXXXXX",
                 {"kind": "account", "account_id": "A-XXXXXX", "api_key": "sk_x"},
                 unique_id="A-XXXXXX"),
  ]
  for index in range(38):
    old_entries.append(
      StubOldEntry(
        f"ct-{index}",
        f"Tracker {index} Cost Tracker (A-XXXXXX)",
        {
          "kind": "cost_tracker",
          "account_id": "A-XXXXXX",
          "name": f"Tracker {index}",
          "mpan": "1111111111111",
          "target_entity_id": f"sensor.tracked_{index}",
        },
        unique_id=f"edf_energy_ct_A-XXXXXX_sensor.tracked_{index}",
      )
    )

  hass = StubHass(old_entries, log)

  assert await async_take_over_old_entries(hass, FOLDER_OURS) == 39

  # The flows are scheduled as tasks, so let them run before reading what they were handed.
  await asyncio.sleep(0)

  payloads = [entry[3] for entry in log if entry[0] == "flow"]
  assert len(payloads) == 39

  by_unique_id = {payload["unique_id"]: payload for payload in payloads}
  assert len(by_unique_id) == 39, "a payload was lost or duplicated"

  for old_entry in old_entries:
    payload = by_unique_id[old_entry.unique_id]
    assert payload["data"] == old_entry.data, f"{old_entry.title} did not carry its data across"
    assert payload["title"] == old_entry.title
    # The two fields issue #53 was missing, called out so a regression names itself.
    assert payload["data"]["kind"] == old_entry.data["kind"]
    assert payload["data"]["account_id"] == "A-XXXXXX"


@pytest.mark.asyncio
async def test_the_hand_over_copies_rather_than_sharing_the_old_data(empty_registries):
  """A shared dict would let one entry's repair rewrite another's data."""
  log = []
  shared = {"kind": "cost_tracker", "account_id": "A-XXXXXX"}
  old_entries = [
    StubOldEntry("one", "One", shared, unique_id="edf_energy_ct_A-XXXXXX_sensor.one"),
    StubOldEntry("two", "Two", shared, unique_id="edf_energy_ct_A-XXXXXX_sensor.two"),
  ]
  hass = StubHass(old_entries, log)

  await async_take_over_old_entries(hass, FOLDER_OURS)
  await asyncio.sleep(0)

  payloads = [entry[3]["data"] for entry in log if entry[0] == "flow"]

  assert len(payloads) == 2
  assert payloads[0] is not payloads[1]
  assert payloads[0] is not shared


# ── Ignored suggestions (issue #53) ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_an_ignored_suggestion_comes_across_ignored_not_as_a_real_entry(empty_registries):
  """The cause of issue #53.

  Home Assistant stores a suggestion the user turned down as an entry with no data. The
  hand-over used to recreate every old entry as an import, so each one became a real entry
  with nothing in it, failing to set up on every start and taking the account down with it.
  """
  log = []
  old_entries = [
    StubOldEntry("account", "A-XXXXXX", {"kind": "account", "account_id": "A-XXXXXX"},
                 unique_id="A-XXXXXX"),
    StubOldEntry("dismissed", "Solar Forecast Next Hour Cost Tracker (A-XXXXXX)", {},
                 unique_id="edf_energy_ct_A-XXXXXX_sensor.solar_forecast", source="ignore"),
  ]
  hass = StubHass(old_entries, log)

  await async_take_over_old_entries(hass, FOLDER_OURS)
  await asyncio.sleep(0)

  flows = [(entry[2], entry[3]) for entry in log if entry[0] == "flow"]
  assert ("import", flows[0][1]) == flows[0] and flows[0][1]["unique_id"] == "A-XXXXXX"
  assert flows[1] == ("ignore", {
    "unique_id": "edf_energy_ct_A-XXXXXX_sensor.solar_forecast",
    "title": "Solar Forecast Next Hour Cost Tracker (A-XXXXXX)",
  })

@pytest.mark.asyncio
async def test_an_ignored_suggestion_with_no_unique_id_is_not_turned_into_an_entry(empty_registries):
  """It cannot be ignored again without one, and importing it is the bug - so it goes."""
  log = []
  hass = StubHass([StubOldEntry("dismissed", "Something", {}, source="ignore")], log)

  await async_take_over_old_entries(hass, FOLDER_OURS)
  await asyncio.sleep(0)

  assert [entry for entry in log if entry[0] == "flow"] == []
  assert ("remove", "dismissed") in log


# ── Installs that already came through the hand-over ──────────────────────────

class StubEntry:
  def __init__(self, source, data, unique_id):
    self.source = source
    self.data = data
    self.unique_id = unique_id

def test_an_empty_import_with_a_unique_id_is_a_carried_over_ignored_suggestion():
  from custom_components.edfenergy_uk.migration import is_carried_over_ignored_suggestion

  assert is_carried_over_ignored_suggestion(StubEntry("import", {}, "edf_energy_ct_A-XXXXXX_sensor.x"))

def test_a_real_imported_entry_is_not_mistaken_for_one():
  """Every entry the hand-over recreated is an import, and the real ones carry their data."""
  from custom_components.edfenergy_uk.migration import is_carried_over_ignored_suggestion

  assert not is_carried_over_ignored_suggestion(StubEntry("import", {"kind": "account"}, "A-XXXXXX"))

def test_an_entry_the_user_set_up_is_never_mistaken_for_one():
  from custom_components.edfenergy_uk.migration import is_carried_over_ignored_suggestion

  assert not is_carried_over_ignored_suggestion(StubEntry("user", {}, "A-XXXXXX"))
  assert not is_carried_over_ignored_suggestion(StubEntry("ignore", {}, "edf_energy_ct_A-XXXXXX_sensor.x"))

def test_one_with_no_unique_id_is_left_alone_because_it_cannot_be_ignored_again():
  from custom_components.edfenergy_uk.migration import is_carried_over_ignored_suggestion

  assert not is_carried_over_ignored_suggestion(StubEntry("import", {}, None))

@pytest.mark.asyncio
async def test_setting_one_up_puts_it_back_to_ignored_and_goes_no_further():
  """It is converted on its own setup, and must not touch anything an account would."""
  from custom_components.edfenergy_uk import async_setup_entry

  class Entry(StubEntry):
    entry_id = "carried-over"
    title = "Solar Forecast Next Hour Cost Tracker (A-XXXXXX)"

  class Hass:
    def __init__(self):
      self.data = {}
      self.scheduled = []
    def async_create_task(self, coro):
      self.scheduled.append(coro.cr_code.co_name)
      coro.close()

  hass = Hass()

  result = await async_setup_entry(hass, Entry("import", {}, "edf_energy_ct_A-XXXXXX_sensor.solar_forecast"))

  assert result is False
  assert hass.scheduled == ["async_restore_ignored_suggestion"]
  assert hass.data == {}


# ── the other EDF integration on the same domain ─────────────────────────────
#
# Another integration in the HACS catalog uses edf_energy as well. Everything the hand-over
# does is destructive to whatever it is pointed at, so it must only ever be pointed at ours.

def _theirs(entry_id="theirs"):
  # Its flow is at version 1 and keeps credentials rather than a kind.
  return StubOldEntry(entry_id, "EDF", {"email": "x@example.com", "password": "p",
                                        "account_id": "A-XXXXXX"}, version=1)


@pytest.mark.asyncio
async def test_the_other_integrations_entries_are_neither_removed_nor_imported(empty_registries):
  log = []
  hass = StubHass([StubOldEntry("ours", "A-XXXXXX", {"kind": "account"}), _theirs()], log)

  assert await async_take_over_old_entries(hass, FOLDER_NOT_OURS) == 1
  await asyncio.sleep(0)

  assert ("remove", "theirs") not in log
  assert ("remove", "ours") in log
  imported = [row[3] for row in log if row[0] == "flow"]
  assert [payload["data"] for payload in imported] == [{"kind": "account"}]


@pytest.mark.asyncio
async def test_with_only_the_other_integration_there_nothing_happens(empty_registries):
  log = []
  hass = StubHass([_theirs()], log)

  assert await async_take_over_old_entries(hass, FOLDER_NOT_OURS) == 0
  assert log == []


@pytest.mark.asyncio
async def test_the_other_integrations_entities_and_devices_are_not_captured(monkeypatch):
  # They share the platform, and some of their unique_ids are the same as ours.
  monkeypatch.setattr(
    "custom_components.edfenergy_uk.migration.er.async_get",
    lambda hass: StubEntityRegistry([
      StubEntity(PREDECESSOR_DOMAIN, "edf_energy_a", "sensor.mine", config_entry_id="ours"),
      StubEntity(PREDECESSOR_DOMAIN, "edf_energy_b", "sensor.theirs", config_entry_id="theirs",
                 name="Their name"),
    ]),
  )
  monkeypatch.setattr(
    "custom_components.edfenergy_uk.migration.dr.async_get",
    lambda hass: StubDeviceRegistry([
      StubDevice("d1", {(PREDECESSOR_DOMAIN, "mine")}, config_entries={"ours"}),
      StubDevice("d2", {(PREDECESSOR_DOMAIN, "theirs")}, config_entries={"theirs"}),
    ]),
  )
  _issue_registry(monkeypatch, [])
  hass = StubHass([StubOldEntry("ours", "A-XXXXXX", {"kind": "account"}), _theirs()], [])

  await async_take_over_old_entries(hass, FOLDER_NOT_OURS)

  captured = hass.data[DOMAIN][DATA_MIGRATION]
  assert list(captured["entities"]) == ["edf_energy_a"]
  assert list(captured["devices"]) == ["mine"]


@pytest.mark.asyncio
async def test_the_other_integrations_notices_are_left_alone(monkeypatch):
  # Nothing tells its repairs apart from ours, so while it is there none are cleared.
  monkeypatch.setattr("custom_components.edfenergy_uk.migration.er.async_get",
                      lambda hass: StubEntityRegistry([]))
  monkeypatch.setattr("custom_components.edfenergy_uk.migration.dr.async_get",
                      lambda hass: StubDeviceRegistry([]))
  deleted = _issue_registry(monkeypatch, [(PREDECESSOR_DOMAIN, "invalid_api_key_a-xxxxxx")])

  # Its entry still set up
  hass = StubHass([StubOldEntry("ours", "A-XXXXXX", {"kind": "account"}), _theirs()], [])
  await async_take_over_old_entries(hass, None)
  # Its folder installed, with no entry of its own yet
  hass = StubHass([StubOldEntry("ours", "A-XXXXXX", {"kind": "account"})], [])
  await async_take_over_old_entries(hass, FOLDER_NOT_OURS)

  assert deleted == []
