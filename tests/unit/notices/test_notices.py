import pytest

from custom_components.edf_energy.notices import _is_newer, build_release_notice
from custom_components.edf_energy.coordinators.power_perks import parse_feed_notice


# ── Comparing versions ────────────────────────────────────────────────────────

@pytest.mark.parametrize("latest,installed,expected", [
  ("19.3.0", "19.2.6", True),
  ("19.2.6", "19.2.6", False),
  ("19.2.5", "19.2.6", False),
  # The one a string compare gets wrong: "19.9.0" sorts above "19.10.0" as text.
  ("19.10.0", "19.9.0", True),
  ("19.9.0", "19.10.0", False),
  # HACS prefixes some repositories' versions with a v.
  ("v19.3.0", "19.2.6", True),
  ("19.3", "19.2.6", True),
  ("20.0", "19.9.9", True),
])
def test_version_comparison(latest, installed, expected):
  assert _is_newer(latest, installed) == expected


@pytest.mark.parametrize("latest,installed", [
  (None, "19.2.6"), ("19.3.0", None), ("unknown", "19.2.6"), ("19.2.6", "unknown"), ("", "19.2.6"),
])
def test_a_version_that_cannot_be_read_never_claims_an_update(latest, installed):
  # Telling somebody to update on the strength of a version we could not parse is worse
  # than staying quiet.
  assert _is_newer(latest, installed) == False


# ── The relay's notice ────────────────────────────────────────────────────────

def test_a_feed_without_a_notice_produces_none():
  assert parse_feed_notice({"sessions": []}) is None
  assert parse_feed_notice(None) is None
  assert parse_feed_notice({"notice": "just a string"}) is None

def test_a_notice_without_a_message_is_not_a_notice():
  assert parse_feed_notice({"notice": {"message": "   ", "id": "x"}}) is None
  assert parse_feed_notice({"notice": {"id": "x"}}) is None

def test_a_notice_is_read():
  notice = parse_feed_notice({"notice": {
    "id": "dispatch-fix", "severity": "urgent", "message": "Update to 19.3.1.",
    "url": "https://github.com/stevekirtley/HomeAssistant-EDFEnergy/releases/19.3.1",
  }})

  assert notice["id"] == "dispatch-fix"
  assert notice["severity"] == "urgent"
  assert notice["message"] == "Update to 19.3.1."
  assert notice["url"].startswith("https://")

def test_an_unknown_severity_becomes_info():
  # The panel styles on severity, so an unexpected one must land somewhere known rather
  # than styling as nothing.
  assert parse_feed_notice({"notice": {"message": "hi", "severity": "critical!!"}})["severity"] == "info"

@pytest.mark.parametrize("url", [
  "http://example.invalid/x",          # plaintext
  "javascript:alert(1)",               # the reason this is checked at all
  "//example.invalid/x",
  "data:text/html,<script>x</script>",
  12345,
])
def test_only_an_https_url_survives(url):
  assert parse_feed_notice({"notice": {"message": "hi", "url": url}})["url"] is None

def test_a_long_message_is_cut_short():
  notice = parse_feed_notice({"notice": {"message": "x" * 5000}})

  assert len(notice["message"]) == 300

def test_a_notice_with_no_id_falls_back_to_its_message():
  # The id is what a dismissal is remembered against, so there has to be one.
  notice = parse_feed_notice({"notice": {"message": "Update now please"}})

  assert notice["id"] == "Update now please"


# ── The release banner ────────────────────────────────────────────────────────

class StubState:
  def __init__(self, attributes):
    self.attributes = attributes

class StubStates:
  def __init__(self, states):
    self._states = states
  def get(self, entity_id):
    return self._states.get(entity_id)

class StubHass:
  def __init__(self, attributes):
    self.states = StubStates({"update.edf_energy_update": StubState(attributes)})

def _release(monkeypatch, attributes, found="update.edf_energy_update"):
  monkeypatch.setattr("custom_components.edf_energy.notices.find_hacs_update_entity", lambda hass: found)
  return build_release_notice(StubHass(attributes))

def test_no_hacs_means_no_release_banner(monkeypatch):
  assert _release(monkeypatch, {}, found=None) is None

def test_an_available_update_is_reported(monkeypatch):
  release = _release(monkeypatch, {
    "installed_version": "19.2.6", "latest_version": "19.3.0",
    "release_url": "https://example.invalid/19.3.0", "skipped_version": None,
  })

  assert release["installed"] == "19.2.6"
  assert release["latest"] == "19.3.0"
  assert release["url"] == "https://example.invalid/19.3.0"

def test_being_up_to_date_says_nothing(monkeypatch):
  assert _release(monkeypatch, {"installed_version": "19.3.0", "latest_version": "19.3.0"}) is None

def test_a_version_the_user_skipped_in_hacs_is_not_raised_again(monkeypatch):
  # Skipping is an answer. Asking again somewhere else is just nagging.
  assert _release(monkeypatch, {
    "installed_version": "19.2.6", "latest_version": "19.3.0", "skipped_version": "19.3.0",
  }) is None

def test_skipping_an_older_version_does_not_hide_a_newer_one(monkeypatch):
  release = _release(monkeypatch, {
    "installed_version": "19.2.6", "latest_version": "19.4.0", "skipped_version": "19.3.0",
  })

  assert release is not None and release["latest"] == "19.4.0"


# ── Finding the HACS entity ───────────────────────────────────────────────────
# The lookup matters as much as the comparison: the wrong entity means either silence or a
# banner about somebody else's integration. The shapes here are taken from a real install.

from custom_components.edf_energy.notices import find_hacs_update_entity


class StubRegistryEntry:
  def __init__(self, entity_id, platform, domain="update", device_id=None, disabled_by=None):
    self.entity_id = entity_id
    self.platform = platform
    self.domain = domain
    self.device_id = device_id
    self.disabled_by = disabled_by

class StubEntityRegistry:
  def __init__(self, entries):
    self.entities = {e.entity_id: e for e in entries}

class StubDevice:
  def __init__(self, name):
    self.name = name

class StubDeviceRegistry:
  def __init__(self, devices):
    self._devices = devices
  def async_get(self, device_id):
    return self._devices.get(device_id)

def _hass_with(entries, states, devices=None):
  hass = type("H", (), {})()
  hass.states = StubStates(states)
  return hass, StubEntityRegistry(entries), StubDeviceRegistry(devices or {})

def _patch(monkeypatch, entities, devices):
  monkeypatch.setattr("custom_components.edf_energy.notices.er.async_get", lambda hass: entities)
  monkeypatch.setattr("custom_components.edf_energy.notices.dr.async_get", lambda hass: devices)

# The real entity picture from a live install.
BRANDS = "https://brands.home-assistant.io/_/edf_energy/icon.png"

def test_the_hacs_entity_is_found_by_its_brands_picture(monkeypatch):
  hass, ents, devs = _hass_with(
    [StubRegistryEntry("update.edf_energy_update", "hacs")],
    {"update.edf_energy_update": StubState({"entity_picture": BRANDS, "installed_version": "19.2.6"})},
  )
  _patch(monkeypatch, ents, devs)

  assert find_hacs_update_entity(hass) == "update.edf_energy_update"

def test_a_renamed_entity_is_still_found(monkeypatch):
  # The default id is only a default; matching on it would lose a renamed entity.
  hass, ents, devs = _hass_with(
    [StubRegistryEntry("update.my_edf_thing", "hacs")],
    {"update.my_edf_thing": StubState({"entity_picture": BRANDS, "installed_version": "19.2.6"})},
  )
  _patch(monkeypatch, ents, devs)

  assert find_hacs_update_entity(hass) == "update.my_edf_thing"

def test_another_repository_is_not_mistaken_for_this_one(monkeypatch):
  hass, ents, devs = _hass_with(
    [StubRegistryEntry("update.predbat_update", "hacs")],
    {"update.predbat_update": StubState({
      "entity_picture": "https://brands.home-assistant.io/_/predbat/icon.png",
      "installed_version": "19.2.6",   # same version, different integration
    })},
  )
  _patch(monkeypatch, ents, devs)

  assert find_hacs_update_entity(hass) is None

def test_a_non_hacs_update_entity_is_ignored(monkeypatch):
  # Core's own update entities must never be read as ours.
  hass, ents, devs = _hass_with(
    [StubRegistryEntry("update.home_assistant_core_update", "hassio")],
    {"update.home_assistant_core_update": StubState({"installed_version": "2026.9.4"})},
  )
  _patch(monkeypatch, ents, devs)

  assert find_hacs_update_entity(hass) is None

def test_a_disabled_entity_is_ignored(monkeypatch):
  hass, ents, devs = _hass_with(
    [StubRegistryEntry("update.edf_energy_update", "hacs", disabled_by="user")],
    {"update.edf_energy_update": StubState({"entity_picture": BRANDS})},
  )
  _patch(monkeypatch, ents, devs)

  assert find_hacs_update_entity(hass) is None

def test_without_a_picture_it_falls_back_to_the_device(monkeypatch):
  hass, ents, devs = _hass_with(
    [StubRegistryEntry("update.edf_energy_update", "hacs", device_id="d1")],
    {"update.edf_energy_update": StubState({"installed_version": "19.2.6"})},
    {"d1": StubDevice("EDF Energy")},
  )
  _patch(monkeypatch, ents, devs)

  assert find_hacs_update_entity(hass) == "update.edf_energy_update"

def test_the_fallback_will_not_match_a_different_version(monkeypatch):
  # Without the picture the device name is the only signal, so the version has to agree -
  # otherwise a repository that happens to share the name would be picked up.
  hass, ents, devs = _hass_with(
    [StubRegistryEntry("update.edf_energy_update", "hacs", device_id="d1")],
    {"update.edf_energy_update": StubState({"installed_version": "1.0.0"})},
    {"d1": StubDevice("EDF Energy")},
  )
  _patch(monkeypatch, ents, devs)

  assert find_hacs_update_entity(hass) is None

def test_no_hacs_at_all_is_not_an_error(monkeypatch):
  hass, ents, devs = _hass_with([], {})
  _patch(monkeypatch, ents, devs)

  assert find_hacs_update_entity(hass) is None
