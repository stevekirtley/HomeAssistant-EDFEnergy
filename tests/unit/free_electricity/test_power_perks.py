"""Power Perks sessions: parsing the relay feed, surviving its absence, and reaching the
free electricity sessions feed alongside the other sources."""
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.edf_energy.api_client.free_electricity_sessions import FreeElectricitySession
from custom_components.edf_energy.const import (
  DATA_FREE_ELECTRICITY_SESSIONS_HISTORY,
  DATA_POWER_PERKS,
  DATA_POWER_PERKS_MANUAL_SESSIONS,
  DOMAIN,
  EVENT_ALL_FREE_ELECTRICITY_SESSIONS,
  EVENT_NEW_FREE_ELECTRICITY_SESSION,
  REFRESH_RATE_IN_MINUTES_POWER_PERKS,
)
from custom_components.edf_energy.coordinators.free_electricity_sessions import (
  _normalise_power_perks,
  refresh_free_electricity_sessions,
)
from custom_components.edf_energy.coordinators.power_perks import (
  PowerPerksCoordinatorResult,
  async_refresh_power_perks,
  make_power_perks_session,
  parse_power_perks_feed,
  register_manual_session,
  session_code,
)

ACCOUNT_ID = "A-XXXXXX"

# The first real session: 19 September 2026, 4am-4pm BST.
FEED = {
  "generated_at": "2026-09-18T14:00:00+01:00",
  "source": "power_perks",
  "sessions": [
    {
      "code": "power_perks_202609190400",
      "start": "2026-09-19T04:00:00+01:00",
      "end": "2026-09-19T16:00:00+01:00",
      "source": "power_perks",
      "received_at": "2026-09-18T09:30:00+01:00",
      "text": "It's Power Perks time! Great news, you've got free electricity tomorrow, 19 September, between 4am-4pm. Enjoy.",
    }
  ],
}

START_UTC = datetime(2026, 9, 19, 3, 0, tzinfo=timezone.utc)
END_UTC = datetime(2026, 9, 19, 15, 0, tzinfo=timezone.utc)


class FakeHass:
  def __init__(self, account_data: dict):
    self.data = {DOMAIN: {ACCOUNT_ID: account_data}}


# ── parse_power_perks_feed ───────────────────────────────────────────────────

def test_feed_session_is_parsed_to_utc():
  sessions = parse_power_perks_feed(FEED)

  assert len(sessions) == 1
  assert sessions[0].code == "power_perks_202609190400"
  assert sessions[0].source == "power_perks"
  assert sessions[0].start == START_UTC
  assert sessions[0].end == END_UTC
  assert sessions[0].duration_in_minutes == 12 * 60


def test_bare_timestamps_are_read_as_uk_time():
  feed = {"sessions": [{"code": "x", "start": "2026-09-19T04:00:00", "end": "2026-09-19T16:00:00"}]}

  sessions = parse_power_perks_feed(feed)

  assert sessions[0].start == START_UTC
  assert sessions[0].end == END_UTC


def test_missing_code_is_derived_from_start():
  feed = {"sessions": [{"start": "2026-09-19T04:00:00+01:00", "end": "2026-09-19T16:00:00+01:00"}]}

  sessions = parse_power_perks_feed(feed)

  assert sessions[0].code == "power_perks_202609190400"


@pytest.mark.parametrize("entry", [
  "not a dict",
  {"start": "2026-09-19T04:00:00+01:00"},
  {"start": "garbage", "end": "2026-09-19T16:00:00+01:00"},
  {"start": "2026-09-19T16:00:00+01:00", "end": "2026-09-19T04:00:00+01:00"},
  {"start": "2026-09-19T04:00:00+01:00", "end": "2026-09-19T04:00:00+01:00"},
])
def test_malformed_entry_is_skipped_without_losing_the_rest(entry):
  feed = {"sessions": [entry] + FEED["sessions"]}

  sessions = parse_power_perks_feed(feed)

  assert [s.code for s in sessions] == ["power_perks_202609190400"]


@pytest.mark.parametrize("payload", [None, "html", [], {}, {"sessions": "nope"}, {"error": "rate limited"}])
def test_unrecognised_payload_returns_none(payload):
  assert parse_power_perks_feed(payload) is None


def test_empty_feed_is_an_empty_list_not_none():
  assert parse_power_perks_feed({"sessions": []}) == []


def test_sessions_are_sorted_by_start():
  feed = {"sessions": [
    {"start": "2026-09-26T04:00:00+01:00", "end": "2026-09-26T16:00:00+01:00"},
    {"start": "2026-09-19T04:00:00+01:00", "end": "2026-09-19T16:00:00+01:00"},
  ]}

  sessions = parse_power_perks_feed(feed)

  assert [s.code for s in sessions] == ["power_perks_202609190400", "power_perks_202609260400"]


# ── async_refresh_power_perks ────────────────────────────────────────────────

async def _feed(payload):
  return payload


@pytest.mark.asyncio
async def test_successful_fetch_populates_sessions():
  current = datetime(2026, 9, 18, 13, 0, tzinfo=timezone.utc)

  result = await async_refresh_power_perks(current, lambda: _feed(FEED), [], None)

  assert result.feed_available is True
  assert result.last_error is None
  assert [s.code for s in result.sessions] == ["power_perks_202609190400"]
  assert result.next_refresh == current + timedelta(minutes=REFRESH_RATE_IN_MINUTES_POWER_PERKS)


@pytest.mark.asyncio
async def test_feed_failure_keeps_last_known_sessions():
  current = datetime(2026, 9, 18, 13, 0, tzinfo=timezone.utc)
  existing = await async_refresh_power_perks(current, lambda: _feed(FEED), [], None)

  result = await async_refresh_power_perks(existing.next_refresh, lambda: _feed(None), [], existing)

  assert result.feed_available is False
  assert result.last_error is not None
  assert result.request_attempts == 2
  assert [s.code for s in result.sessions] == ["power_perks_202609190400"]


@pytest.mark.asyncio
async def test_unrecognised_payload_is_treated_as_failure():
  current = datetime(2026, 9, 18, 13, 0, tzinfo=timezone.utc)
  existing = await async_refresh_power_perks(current, lambda: _feed(FEED), [], None)

  result = await async_refresh_power_perks(existing.next_refresh, lambda: _feed({"error": "forbidden"}), [], existing)

  assert result.feed_available is False
  assert [s.code for s in result.sessions] == ["power_perks_202609190400"]


@pytest.mark.asyncio
async def test_failure_retries_sooner_than_the_normal_interval():
  current = datetime(2026, 9, 18, 13, 0, tzinfo=timezone.utc)

  result = await async_refresh_power_perks(current, lambda: _feed(None), [], None)

  assert result.next_refresh < current + timedelta(minutes=REFRESH_RATE_IN_MINUTES_POWER_PERKS)
  assert result.next_refresh > current


@pytest.mark.asyncio
async def test_no_fetch_before_next_refresh():
  current = datetime(2026, 9, 18, 13, 0, tzinfo=timezone.utc)
  existing = await async_refresh_power_perks(current, lambda: _feed(FEED), [], None)
  calls = []

  async def counting_feed():
    calls.append(1)
    return FEED

  result = await async_refresh_power_perks(current + timedelta(minutes=1), counting_feed, [], existing)

  assert result is existing
  assert calls == []


@pytest.mark.asyncio
async def test_manual_session_is_reflected_without_waiting_for_the_next_poll():
  current = datetime(2026, 9, 18, 13, 0, tzinfo=timezone.utc)
  existing = await async_refresh_power_perks(current, lambda: _feed({"sessions": []}), [], None)
  manual = [make_power_perks_session(START_UTC, END_UTC)]

  result = await async_refresh_power_perks(current + timedelta(minutes=1), lambda: _feed(FEED), manual, existing)

  assert result.sessions == []
  assert [s.code for s in result.manual_sessions] == ["power_perks_202609190400"]
  assert [s.code for s in result.all_sessions] == ["power_perks_202609190400"]


def test_manual_session_wins_over_feed_on_the_same_code():
  feed_session = FreeElectricitySession("power_perks_202609190400", START_UTC, END_UTC, "power_perks")
  manual_session = make_power_perks_session(START_UTC, END_UTC + timedelta(hours=1))
  result = PowerPerksCoordinatorResult(datetime.now(timezone.utc), 1, [feed_session], [manual_session])

  merged = result.all_sessions

  assert len(merged) == 1
  assert merged[0].end == END_UTC + timedelta(hours=1)


# ── register_manual_session ──────────────────────────────────────────────────

def test_session_code_uses_uk_local_time():
  # 03:00Z on 19 September is 04:00 BST, matching the relay's code.
  assert session_code(START_UTC) == "power_perks_202609190400"


def test_register_manual_session_replaces_same_start():
  hass = FakeHass({})

  first = register_manual_session(hass, ACCOUNT_ID, START_UTC, END_UTC)
  second = register_manual_session(hass, ACCOUNT_ID, START_UTC, END_UTC + timedelta(hours=2))
  stored = hass.data[DOMAIN][ACCOUNT_ID][DATA_POWER_PERKS_MANUAL_SESSIONS.format(ACCOUNT_ID)]

  assert first.code == second.code
  assert len(stored) == 1
  assert stored[0].end == END_UTC + timedelta(hours=2)


def test_register_manual_session_keeps_sessions_sorted():
  hass = FakeHass({})

  register_manual_session(hass, ACCOUNT_ID, START_UTC + timedelta(days=7), END_UTC + timedelta(days=7))
  register_manual_session(hass, ACCOUNT_ID, START_UTC, END_UTC)
  stored = hass.data[DOMAIN][ACCOUNT_ID][DATA_POWER_PERKS_MANUAL_SESSIONS.format(ACCOUNT_ID)]

  assert [s.start for s in stored] == [START_UTC, START_UTC + timedelta(days=7)]


# ── through the free electricity sessions coordinator ────────────────────────

def test_normalise_power_perks_handles_missing_result():
  assert _normalise_power_perks(None) == []


def test_power_perks_sessions_reach_the_free_electricity_feed():
  current = datetime(2026, 9, 18, 13, 0, tzinfo=timezone.utc)
  power_perks = PowerPerksCoordinatorResult(current, 1, parse_power_perks_feed(FEED))
  hass = FakeHass({
    DATA_POWER_PERKS.format(ACCOUNT_ID): power_perks,
    DATA_FREE_ELECTRICITY_SESSIONS_HISTORY.format(ACCOUNT_ID): [],
  })
  fired = []

  result = refresh_free_electricity_sessions(current, hass, ACCOUNT_ID, None, lambda t, p: fired.append((t, p)))

  assert [e.code for e in result.events] == ["power_perks_202609190400"]
  new_session_events = [p for t, p in fired if t == EVENT_NEW_FREE_ELECTRICITY_SESSION]
  assert len(new_session_events) == 1
  assert new_session_events[0]["event_source"] == "power_perks"
  assert new_session_events[0]["event_duration_in_minutes"] == 12 * 60
  all_sessions = [p for t, p in fired if t == EVENT_ALL_FREE_ELECTRICITY_SESSIONS]
  assert all_sessions[0]["events"][0]["source"] == "power_perks"
  # And it is now in the persisted history, so it survives the feed going away.
  history = hass.data[DOMAIN][ACCOUNT_ID][DATA_FREE_ELECTRICITY_SESSIONS_HISTORY.format(ACCOUNT_ID)]
  assert [s.code for s in history] == ["power_perks_202609190400"]


def test_power_perks_session_survives_feed_dropping_it():
  """Once seen, a session stays in the day's feed from history even if the relay loses it."""
  current = datetime(2026, 9, 19, 8, 0, tzinfo=timezone.utc)   # mid-session
  seeded = PowerPerksCoordinatorResult(current, 1, parse_power_perks_feed(FEED))
  hass = FakeHass({
    DATA_POWER_PERKS.format(ACCOUNT_ID): seeded,
    DATA_FREE_ELECTRICITY_SESSIONS_HISTORY.format(ACCOUNT_ID): [],
  })
  first = refresh_free_electricity_sessions(current, hass, ACCOUNT_ID, None, lambda t, p: None)

  hass.data[DOMAIN][ACCOUNT_ID][DATA_POWER_PERKS.format(ACCOUNT_ID)] = PowerPerksCoordinatorResult(current, 2, [], feed_available=False)
  second = refresh_free_electricity_sessions(current + timedelta(minutes=1), hass, ACCOUNT_ID, first, lambda t, p: None)

  assert [e.code for e in second.events] == ["power_perks_202609190400"]


def test_withdrawn_future_session_is_retracted_from_history():
  """A session the relay stops publishing before it starts must leave the feed too."""
  current = datetime(2026, 9, 18, 16, 30, tzinfo=timezone.utc)
  seeded = PowerPerksCoordinatorResult(current, 1, parse_power_perks_feed(FEED))
  hass = FakeHass({
    DATA_POWER_PERKS.format(ACCOUNT_ID): seeded,
    DATA_FREE_ELECTRICITY_SESSIONS_HISTORY.format(ACCOUNT_ID): [],
  })
  first = refresh_free_electricity_sessions(current, hass, ACCOUNT_ID, None, lambda t, p: None)
  assert [e.code for e in first.events] == ["power_perks_202609190400"]

  hass.data[DOMAIN][ACCOUNT_ID][DATA_POWER_PERKS.format(ACCOUNT_ID)] = PowerPerksCoordinatorResult(current, 1, [], feed_available=True)
  second = refresh_free_electricity_sessions(current + timedelta(minutes=1), hass, ACCOUNT_ID, first, lambda t, p: None)

  assert second.events == []
  assert hass.data[DOMAIN][ACCOUNT_ID][DATA_FREE_ELECTRICITY_SESSIONS_HISTORY.format(ACCOUNT_ID)] == []


def test_feed_outage_does_not_retract_anything():
  current = datetime(2026, 9, 18, 16, 30, tzinfo=timezone.utc)
  seeded = PowerPerksCoordinatorResult(current, 1, parse_power_perks_feed(FEED))
  hass = FakeHass({
    DATA_POWER_PERKS.format(ACCOUNT_ID): seeded,
    DATA_FREE_ELECTRICITY_SESSIONS_HISTORY.format(ACCOUNT_ID): [],
  })
  first = refresh_free_electricity_sessions(current, hass, ACCOUNT_ID, None, lambda t, p: None)

  hass.data[DOMAIN][ACCOUNT_ID][DATA_POWER_PERKS.format(ACCOUNT_ID)] = PowerPerksCoordinatorResult(current, 2, [], feed_available=False)
  second = refresh_free_electricity_sessions(current + timedelta(minutes=1), hass, ACCOUNT_ID, first, lambda t, p: None)

  assert [e.code for e in second.events] == ["power_perks_202609190400"]


def test_started_session_is_kept_even_if_feed_drops_it():
  current = datetime(2026, 9, 19, 8, 0, tzinfo=timezone.utc)   # mid-session
  seeded = PowerPerksCoordinatorResult(current, 1, parse_power_perks_feed(FEED))
  hass = FakeHass({
    DATA_POWER_PERKS.format(ACCOUNT_ID): seeded,
    DATA_FREE_ELECTRICITY_SESSIONS_HISTORY.format(ACCOUNT_ID): [],
  })
  first = refresh_free_electricity_sessions(current, hass, ACCOUNT_ID, None, lambda t, p: None)

  hass.data[DOMAIN][ACCOUNT_ID][DATA_POWER_PERKS.format(ACCOUNT_ID)] = PowerPerksCoordinatorResult(current, 1, [], feed_available=True)
  second = refresh_free_electricity_sessions(current + timedelta(minutes=1), hass, ACCOUNT_ID, first, lambda t, p: None)

  assert [e.code for e in second.events] == ["power_perks_202609190400"]


def test_manual_session_survives_retraction():
  current = datetime(2026, 9, 18, 16, 30, tzinfo=timezone.utc)
  manual = [make_power_perks_session(START_UTC, END_UTC)]
  seeded = PowerPerksCoordinatorResult(current, 1, [], manual, feed_available=True)
  hass = FakeHass({
    DATA_POWER_PERKS.format(ACCOUNT_ID): seeded,
    DATA_FREE_ELECTRICITY_SESSIONS_HISTORY.format(ACCOUNT_ID): [],
  })

  result = refresh_free_electricity_sessions(current, hass, ACCOUNT_ID, None, lambda t, p: None)
  again = refresh_free_electricity_sessions(current + timedelta(minutes=1), hass, ACCOUNT_ID, result, lambda t, p: None)

  assert [e.code for e in again.events] == ["power_perks_202609190400"]
