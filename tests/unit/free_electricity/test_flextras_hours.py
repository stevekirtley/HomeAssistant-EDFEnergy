"""Free hours booked in the Flextras app reaching the free electricity sessions feed.

The payloads here are the real ones captured from EDF's app on 5 October 2026, including
a booking split across two days with a gap in it, and one that straddles the end of BST.
"""
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.edf_energy.api_client.flextras_hours import parse_booked_hours
from custom_components.edf_energy.const import (
  DATA_FLEXTRAS_HOURS,
  DATA_FREE_ELECTRICITY_SESSIONS_HISTORY,
  DATA_POWER_PERKS,
  DOMAIN,
  REFRESH_RATE_IN_MINUTES_FLEXTRAS_HOURS,
)
from custom_components.edf_energy.coordinators.flextras_hours import (
  FlextrasHoursCoordinatorResult,
  async_refresh_flextras_hours,
  session_code,
  windows_to_sessions,
)
from custom_components.edf_energy.coordinators.free_electricity_sessions import (
  _normalise_flextras_hours,
  refresh_free_electricity_sessions,
)

ACCOUNT_ID = "A-XXXXXX"


def screen(items, **counters):
  base = {"bonusHours": 4, "bonusHoursRemaining": 0, "challengeHours": 0,
          "challengeHoursRemaining": 0, "totalRemainingHours": 0}
  base.update(counters)
  return {"screen": "REWARD_HOURS", "version": "1.0", "components": [
    {"id": "reward_hours_banner_1", "type": "REWARD_HOURS_BANNER", "props": {"title": "x"}},
    {"id": "booked_hours_list_1", "type": "BOOKED_HOURS_LIST", "props": dict(base, items=items)},
    {"id": "faq_block_1", "type": "FAQ_LIST", "props": {"items": []}},
  ]}


def slot(date, start, end):
  return {"slotId": f"SLOT-{date}-{start[:2]}-{end[:2]}", "date": date,
          "startTime": start, "endTime": end, "status": "SELECTED"}


# Captured verbatim: two adjacent hours on a Saturday, plus two non-adjacent in November.
REAL = screen([
  {"id": "booked-1-20261010", "date": "2026-10-10T00:00:00.000Z", "dateInText": "Saturday, 10 October",
   "bookedTimeSlots": "9am - 10am, 10am - 11am", "isAfterCutOff": False,
   "rawTimeSlots": [slot("2026-10-10", "09:00", "10:00"), slot("2026-10-10", "10:00", "11:00")]},
  {"id": "booked-2-20261101", "date": "2026-11-01T00:00:00.000Z", "dateInText": "Sunday, 1 November",
   "bookedTimeSlots": "12am - 1am, 2am - 3am", "isAfterCutOff": False,
   "rawTimeSlots": [slot("2026-11-01", "00:00", "01:00"), slot("2026-11-01", "02:00", "03:00")]},
])
NOTHING_BOOKED = screen([], bonusHoursRemaining=4, totalRemainingHours=4)


# ── parsing ──────────────────────────────────────────────────────────────────

def test_adjacent_hours_become_one_window_and_gaps_stay_separate():
  parsed = parse_booked_hours(REAL)

  assert parsed["windows"] == [
    # 09:00-11:00 BST is 08:00-10:00 UTC - two booked hours, one window
    (datetime(2026, 10, 10, 8, 0, tzinfo=timezone.utc), datetime(2026, 10, 10, 10, 0, tzinfo=timezone.utc)),
    # 1 November is after the clocks change, so local time is UTC, and the gap is preserved
    (datetime(2026, 11, 1, 0, 0, tzinfo=timezone.utc), datetime(2026, 11, 1, 1, 0, tzinfo=timezone.utc)),
    (datetime(2026, 11, 1, 2, 0, tzinfo=timezone.utc), datetime(2026, 11, 1, 3, 0, tzinfo=timezone.utc)),
  ]


def test_times_are_read_as_local_not_utc():
  """EDF's own booking response proves 09:00 means 09:00 BST, i.e. 08:00 UTC."""
  parsed = parse_booked_hours(screen([
    {"rawTimeSlots": [slot("2026-10-10", "09:00", "10:00")]}]))

  assert parsed["windows"][0][0] == datetime(2026, 10, 10, 8, 0, tzinfo=timezone.utc)


def test_the_clock_change_is_handled_rather_than_a_fixed_offset():
  """Same wall-clock hour, one in BST and one in GMT, must map to different UTC."""
  bst = parse_booked_hours(screen([{"rawTimeSlots": [slot("2026-10-24", "09:00", "10:00")]}]))["windows"][0][0]
  gmt = parse_booked_hours(screen([{"rawTimeSlots": [slot("2026-10-26", "09:00", "10:00")]}]))["windows"][0][0]

  assert bst.hour == 8
  assert gmt.hour == 9


def test_hour_balances_are_carried_through():
  parsed = parse_booked_hours(REAL)

  assert parsed["bonus_hours"] == 4
  assert parsed["bonus_hours_remaining"] == 0
  assert parsed["total_remaining_hours"] == 0


def test_nothing_booked_is_an_empty_list_not_a_failure():
  parsed = parse_booked_hours(NOTHING_BOOKED)

  assert parsed["windows"] == []
  assert parsed["total_remaining_hours"] == 4


@pytest.mark.parametrize("payload", [
  None, "html", [], {}, {"components": "nope"},
  {"components": [{"type": "FAQ_LIST", "props": {}}]},   # screen without the booked list
])
def test_an_unreadable_payload_is_none_so_the_caller_keeps_what_it_had(payload):
  assert parse_booked_hours(payload) is None


def test_malformed_slots_are_skipped_without_losing_the_rest():
  parsed = parse_booked_hours(screen([{"rawTimeSlots": [
    "not a dict", {"date": "2026-10-10"}, {"date": "bad", "startTime": "09:00", "endTime": "10:00"},
    slot("2026-10-10", "13:00", "14:00"),
  ]}]))

  assert len(parsed["windows"]) == 1
  assert parsed["windows"][0][0] == datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc)


# ── coordinator ──────────────────────────────────────────────────────────────

async def _fetch(payload):
  return payload


@pytest.mark.asyncio
async def test_booked_hours_become_sessions():
  current = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)

  result = await async_refresh_flextras_hours(current, lambda: _fetch(REAL), None)

  assert result.available is True
  assert [s.source for s in result.sessions] == ["flextras_hours"] * 3
  assert result.sessions[0].duration_in_minutes == 120
  assert result.next_refresh == current + timedelta(minutes=REFRESH_RATE_IN_MINUTES_FLEXTRAS_HOURS)


@pytest.mark.asyncio
async def test_an_unreadable_response_keeps_the_existing_booking():
  """A bad response must never look like the customer cancelling."""
  current = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)
  booked = await async_refresh_flextras_hours(current, lambda: _fetch(REAL), None)

  result = await async_refresh_flextras_hours(booked.next_refresh, lambda: _fetch(None), booked)

  assert result.available is False
  assert [s.code for s in result.sessions] == [s.code for s in booked.sessions]


@pytest.mark.asyncio
async def test_cancelling_in_the_app_empties_the_sessions():
  current = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)
  booked = await async_refresh_flextras_hours(current, lambda: _fetch(REAL), None)

  result = await async_refresh_flextras_hours(booked.next_refresh, lambda: _fetch(NOTHING_BOOKED), booked)

  assert result.available is True
  assert result.sessions == []
  assert result.total_remaining_hours == 4


def test_session_code_is_keyed_on_local_start_time():
  start = datetime(2026, 10, 10, 8, 0, tzinfo=timezone.utc)   # 09:00 BST

  assert session_code(start) == "flextras_hours_202610100900"


def test_normalise_handles_a_missing_result():
  assert _normalise_flextras_hours(None) == []


# ── through the free electricity sessions feed ───────────────────────────────

class FakeHass:
  def __init__(self, account_data):
    self.data = {DOMAIN: {ACCOUNT_ID: account_data}}


def _hass(hours_result, history=None):
  return FakeHass({
    DATA_FLEXTRAS_HOURS.format(ACCOUNT_ID): hours_result,
    DATA_FREE_ELECTRICITY_SESSIONS_HISTORY.format(ACCOUNT_ID): history or [],
  })


def test_booked_hours_appear_in_the_sessions_feed():
  current = datetime(2026, 10, 10, 6, 0, tzinfo=timezone.utc)
  sessions = windows_to_sessions(parse_booked_hours(REAL)["windows"])
  hass = _hass(FlextrasHoursCoordinatorResult(current, 1, sessions))
  fired = []

  result = refresh_free_electricity_sessions(current, hass, ACCOUNT_ID, None, lambda t, p: fired.append((t, p)))

  todays = [e for e in result.events if e.start.date() == current.date()]
  assert [e.source for e in todays] == ["flextras_hours"]
  assert todays[0].duration_in_minutes == 120
  windows = [p for t, p in fired if "free_electricity_windows" in (p or {})]
  assert any(w["source"] == "flextras_hours" for w in windows[0]["free_electricity_windows"])


def test_hours_cancelled_before_they_start_are_retracted():
  """The whole point of polling: the calendar has to follow the app."""
  current = datetime(2026, 10, 10, 6, 0, tzinfo=timezone.utc)   # before the 08:00Z window
  sessions = windows_to_sessions(parse_booked_hours(REAL)["windows"])
  hass = _hass(FlextrasHoursCoordinatorResult(current, 1, sessions))
  first = refresh_free_electricity_sessions(current, hass, ACCOUNT_ID, None, lambda t, p: None)
  assert len(first.events) == 3

  hass.data[DOMAIN][ACCOUNT_ID][DATA_FLEXTRAS_HOURS.format(ACCOUNT_ID)] = \
    FlextrasHoursCoordinatorResult(current, 1, [], available=True)
  second = refresh_free_electricity_sessions(current + timedelta(minutes=1), hass, ACCOUNT_ID, first, lambda t, p: None)

  assert second.events == []


def test_an_outage_does_not_retract_a_booking():
  current = datetime(2026, 10, 10, 6, 0, tzinfo=timezone.utc)
  sessions = windows_to_sessions(parse_booked_hours(REAL)["windows"])
  hass = _hass(FlextrasHoursCoordinatorResult(current, 1, sessions))
  first = refresh_free_electricity_sessions(current, hass, ACCOUNT_ID, None, lambda t, p: None)

  hass.data[DOMAIN][ACCOUNT_ID][DATA_FLEXTRAS_HOURS.format(ACCOUNT_ID)] = \
    FlextrasHoursCoordinatorResult(current, 2, [], available=False)
  second = refresh_free_electricity_sessions(current + timedelta(minutes=1), hass, ACCOUNT_ID, first, lambda t, p: None)

  assert len(second.events) == 3


def test_an_hour_already_under_way_is_never_retracted():
  current = datetime(2026, 10, 10, 9, 0, tzinfo=timezone.utc)   # inside the 08:00-10:00 window
  sessions = windows_to_sessions(parse_booked_hours(REAL)["windows"])
  hass = _hass(FlextrasHoursCoordinatorResult(current, 1, sessions))
  first = refresh_free_electricity_sessions(current, hass, ACCOUNT_ID, None, lambda t, p: None)

  hass.data[DOMAIN][ACCOUNT_ID][DATA_FLEXTRAS_HOURS.format(ACCOUNT_ID)] = \
    FlextrasHoursCoordinatorResult(current, 1, [], available=True)
  second = refresh_free_electricity_sessions(current + timedelta(minutes=1), hass, ACCOUNT_ID, first, lambda t, p: None)

  # The two November windows had not started, so they go; the one under way stays.
  assert [e.code for e in second.events] == ["flextras_hours_202610100900"]


def test_moving_an_hour_replaces_the_old_window():
  current = datetime(2026, 10, 10, 6, 0, tzinfo=timezone.utc)
  hass = _hass(FlextrasHoursCoordinatorResult(
    current, 1, windows_to_sessions(parse_booked_hours(
      screen([{"rawTimeSlots": [slot("2026-10-10", "09:00", "10:00")]}]))["windows"])))
  first = refresh_free_electricity_sessions(current, hass, ACCOUNT_ID, None, lambda t, p: None)
  assert [e.code for e in first.events] == ["flextras_hours_202610100900"]

  hass.data[DOMAIN][ACCOUNT_ID][DATA_FLEXTRAS_HOURS.format(ACCOUNT_ID)] = FlextrasHoursCoordinatorResult(
    current, 1, windows_to_sessions(parse_booked_hours(
      screen([{"rawTimeSlots": [slot("2026-10-10", "14:00", "15:00")]}]))["windows"]))
  second = refresh_free_electricity_sessions(current + timedelta(minutes=1), hass, ACCOUNT_ID, first, lambda t, p: None)

  assert [e.code for e in second.events] == ["flextras_hours_202610101400"]
