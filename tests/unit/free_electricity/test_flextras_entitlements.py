"""Hour entitlements and their expiry dates.

Worth its own cover because of what EDF do with hours you leave unspent: challenge hours
are booked for you automatically once they are about to expire, at a time of their
choosing. Knowing an expiry is coming is what lets an automation pick the slot first.
"""
from datetime import datetime, timezone

import pytest

from custom_components.edf_energy.api_client.flextras_hours import parse_entitlements
from custom_components.edf_energy.flextras.hours_sensor import next_expiry

# Captured from the hours screen on 5 October 2026.
REAL = {"screen": "REWARD_HOURS", "components": [
  {"type": "REWARD_HOURS_BANNER", "props": {"title": "Free electricity hours"}},
  {"type": "HOURS_TO_USE_LIST", "props": {
    "title": "Hours remaining", "hoursLeft": 4,
    "items": [{
      "id": "QWNjTm8jQS1FMzUxQjFBOA",
      "type": "bonus",
      "title": "Joining bonus",
      "description": "You have 4 hours left to use",
      "date": "2027-10-01T00:00:00.000Z",
    }],
  }},
]}

NOW = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)


def test_the_entitlement_and_its_expiry_are_read():
  entitlements = parse_entitlements(REAL)

  assert entitlements == [{
    "kind": "bonus",
    "title": "Joining bonus",
    "hours_left": 4.0,
    "expires": "2027-10-01T00:00:00.000Z",
    "description": "You have 4 hours left to use",
  }]


def test_the_hour_count_is_dug_out_of_edf_s_prose():
  """There is no numeric field for it; the screen only says it in words."""
  entitlements = parse_entitlements({"components": [{"type": "HOURS_TO_USE_LIST", "props": {
    "items": [{"description": "You have 1 hour left to use", "date": "2026-12-01T00:00:00.000Z"}]}}]})

  assert entitlements[0]["hours_left"] == 1.0


def test_prose_we_cannot_read_leaves_the_count_unknown_rather_than_wrong():
  entitlements = parse_entitlements({"components": [{"type": "HOURS_TO_USE_LIST", "props": {
    "items": [{"description": "Your hours are ready", "date": "2026-12-01T00:00:00.000Z"}]}}]})

  assert entitlements[0]["hours_left"] is None


def test_several_buckets_are_kept_separate():
  """The aggregate counters flatten these together, which is why they are read at all."""
  entitlements = parse_entitlements({"components": [{"type": "HOURS_TO_USE_LIST", "props": {"items": [
    {"type": "bonus", "title": "Joining bonus", "description": "You have 4 hours left to use",
     "date": "2027-10-01T00:00:00.000Z"},
    {"type": "challenge", "title": "October challenge", "description": "You have 2 hours left to use",
     "date": "2026-11-30T00:00:00.000Z"},
  ]}}]})

  assert [e["kind"] for e in entitlements] == ["bonus", "challenge"]
  assert [e["hours_left"] for e in entitlements] == [4.0, 2.0]


def test_a_screen_without_the_component_is_none_not_empty():
  """None means 'not told', which the caller keeps the last known value for."""
  assert parse_entitlements({"components": [{"type": "FAQ_LIST", "props": {}}]}) is None


@pytest.mark.parametrize("payload", [None, "html", {}, {"components": "nope"}])
def test_an_unreadable_payload_is_none(payload):
  assert parse_entitlements(payload) is None


def test_no_items_is_an_empty_list():
  assert parse_entitlements({"components": [{"type": "HOURS_TO_USE_LIST", "props": {"items": []}}]}) == []


# ── the expiry the sensor reports ────────────────────────────────────────────

def test_the_soonest_expiry_with_hours_against_it_wins():
  expires, hours, days = next_expiry([
    {"hours_left": 4, "expires": "2027-10-01T00:00:00.000Z"},
    {"hours_left": 2, "expires": "2026-11-30T00:00:00.000Z"},
  ], NOW)

  assert expires == datetime(2026, 11, 30, tzinfo=timezone.utc)
  assert hours == 2
  assert days == 55


def test_a_spent_bucket_is_ignored():
  """An expiry that cannot cost anything should not wake an automation."""
  expires, hours, _ = next_expiry([
    {"hours_left": 0, "expires": "2026-10-10T00:00:00.000Z"},
    {"hours_left": 4, "expires": "2027-10-01T00:00:00.000Z"},
  ], NOW)

  assert expires == datetime(2027, 10, 1, tzinfo=timezone.utc)
  assert hours == 4


def test_an_unknown_count_still_counts_as_hours_at_risk():
  """Treating 'could not read it' as zero would hide a real expiry."""
  expires, hours, _ = next_expiry(
    [{"hours_left": None, "expires": "2026-10-20T00:00:00.000Z"}], NOW)

  assert expires == datetime(2026, 10, 20, tzinfo=timezone.utc)
  assert hours is None


def test_nothing_to_expire_reports_nothing():
  assert next_expiry([], NOW) == (None, None, None)
  assert next_expiry(None, NOW) == (None, None, None)


def test_an_expiry_already_past_does_not_go_negative():
  _, _, days = next_expiry([{"hours_left": 1, "expires": "2026-09-01T00:00:00.000Z"}], NOW)

  assert days == 0


def test_a_bucket_without_an_expiry_is_skipped():
  assert next_expiry([{"hours_left": 4, "expires": None}], NOW) == (None, None, None)


# ── what goes into a bug report ──────────────────────────────────────────────
# A customer on a time-of-use tariff cannot join Weekend Saver, so they never earn
# challenge hours and that half of the screen is unobservable on their account. The
# structure therefore travels with diagnostics, which makes the redaction load-bearing.

def test_the_screen_summary_carries_the_entitlement_shape():
  from custom_components.edf_energy.api_client.flextras_hours import redact_hours_screen

  summary = redact_hours_screen(REAL)
  hours = next(c for c in summary["components"] if c["type"] == "HOURS_TO_USE_LIST")

  assert summary["screen"] == "REWARD_HOURS"
  assert hours["items"][0]["type"] == "bonus"
  assert hours["items"][0]["date"] == "2027-10-01T00:00:00.000Z"
  assert "hoursLeft" in hours["keys"]


def test_the_entitlement_id_never_leaves_the_instance():
  """It is base64 of AccNo#<account>#PropId#<property>, so it is an identifier."""
  from custom_components.edf_energy.api_client.flextras_hours import redact_hours_screen

  summary = redact_hours_screen(REAL)

  assert "QWNjTm8jQS1FMzUxQjFBOA" not in repr(summary)
  assert all("id" not in item for c in summary["components"] for item in c.get("items", []))


def test_the_counters_travel_but_the_customer_s_own_hours_do_not():
  """The numbers help fix a parser; when someone is at home does not."""
  from custom_components.edf_energy.api_client.flextras_hours import redact_hours_screen

  screen = {"screen": "REWARD_HOURS", "components": [{"type": "BOOKED_HOURS_LIST", "props": {
    "bonusHours": 4, "totalRemainingHours": 2, "message": "x",
    "items": [{"date": "2026-10-10", "rawTimeSlots": [
      {"date": "2026-10-10", "startTime": "09:00", "endTime": "10:00"}]}],
  }}]}

  summary = redact_hours_screen(screen)
  booked = summary["components"][0]

  assert booked["counters"] == {"bonusHours": 4, "totalRemainingHours": 2}
  assert booked["booked_day_count"] == 1
  assert "09:00" not in repr(summary)


def test_an_unreadable_screen_summarises_to_none():
  from custom_components.edf_energy.api_client.flextras_hours import redact_hours_screen

  assert redact_hours_screen(None) is None
  assert redact_hours_screen("html") is None
