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
