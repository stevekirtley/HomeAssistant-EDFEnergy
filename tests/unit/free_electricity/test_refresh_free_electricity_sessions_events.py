"""Covers how often refresh_free_electricity_sessions fires the "all sessions" bus event.

The event entity's state is the timestamp of the last event, so every fire is by definition a
new state that the recorder cannot dedupe. Firing on every coordinator tick meant 1440 database
rows a day per account, so it now fires only on change plus an hourly heartbeat.
"""
from datetime import datetime, timedelta

from custom_components.edf_energy.api_client.free_electricity_sessions import FreeElectricitySession
from custom_components.edf_energy.const import (
  DATA_FREE_ELECTRICITY_SESSIONS_HISTORY,
  DATA_SUNDAY_SAVER,
  DOMAIN,
  EVENT_ALL_FREE_ELECTRICITY_SESSIONS,
  EVENT_NEW_FREE_ELECTRICITY_SESSION,
  REFRESH_RATE_IN_MINUTES_FREE_ELECTRICITY_SESSIONS,
)
from custom_components.edf_energy.coordinators.free_electricity_sessions import (
  FreeElectricitySessionsCoordinatorResult,
  refresh_free_electricity_sessions,
)

ACCOUNT_ID = "A-XXXXXX"


class FakeHass:
  """Enough of hass for the coordinator: just the data dict it reads providers out of."""

  def __init__(self, account_data: dict):
    self.data = {DOMAIN: {ACCOUNT_ID: account_data}}


def build_hass(history=None):
  data = {}
  if history is not None:
    data[DATA_FREE_ELECTRICITY_SESSIONS_HISTORY.format(ACCOUNT_ID)] = history
  return FakeHass(data)


def session(code, start: datetime, end: datetime, source="sunday_saver"):
  return FreeElectricitySession(code, start, end, source)


def sunday_saver_result(start_str: str, end_str: str):
  """Minimal stub for SundaySaverCoordinatorResult, as read by _normalise_sunday_saver."""
  class _Stub:
    pass
  stub = _Stub()
  stub.has_event = True
  stub.start = datetime.fromisoformat(start_str)
  stub.end = datetime.fromisoformat(end_str)
  return stub


def run(hass, current, existing_result):
  """Run one coordinator tick, returning (result, list of all-sessions payloads fired)."""
  fired = []

  def fire_event(event_type, payload):
    if event_type == EVENT_ALL_FREE_ELECTRICITY_SESSIONS:
      fired.append(payload)

  result = refresh_free_electricity_sessions(current, hass, ACCOUNT_ID, existing_result, fire_event)
  return result, fired


def test_when_first_run_then_event_is_fired():
  # Arrange
  current = datetime.fromisoformat("2026-08-04T12:00:00+00:00")
  hass = build_hass([])

  # Act
  result, fired = run(hass, current, None)

  # Assert
  assert len(fired) == 1
  assert result.last_evaluated == current


def test_when_nothing_changes_then_event_is_not_fired_again():
  """The regression this test exists for - a tick with no change used to write a database row."""
  # Arrange
  current = datetime.fromisoformat("2026-08-04T12:00:00+00:00")
  hass = build_hass([])
  result, _ = run(hass, current, None)

  # Act - ten further ticks a minute apart, well inside the heartbeat window
  total_fired = 0
  for minute in range(1, 11):
    result, fired = run(hass, current + timedelta(minutes=minute), result)
    total_fired += len(fired)

  # Assert
  assert total_fired == 0


def test_when_heartbeat_is_due_then_event_is_fired():
  # Arrange
  current = datetime.fromisoformat("2026-08-04T12:00:00+00:00")
  hass = build_hass([])
  result, _ = run(hass, current, None)

  # Act - step just past the refresh rate without anything changing
  heartbeat_at = current + timedelta(minutes=REFRESH_RATE_IN_MINUTES_FREE_ELECTRICITY_SESSIONS, seconds=1)
  result, fired = run(hass, heartbeat_at, result)

  # Assert
  assert len(fired) == 1
  assert result.last_evaluated == heartbeat_at


def test_when_quiet_then_heartbeat_does_not_drift():
  """last_evaluated must stay anchored to the last fire, or next_refresh slides forward a minute
  every tick and the heartbeat never comes due."""
  # Arrange
  current = datetime.fromisoformat("2026-08-04T12:00:00+00:00")
  hass = build_hass([])
  result, _ = run(hass, current, None)

  # Act - tick every minute for two hours
  fires = 0
  for minute in range(1, 121):
    result, fired = run(hass, current + timedelta(minutes=minute), result)
    fires += len(fired)

  # Assert - roughly one an hour, not one a minute
  assert fires == 2, f"expected 2 heartbeats in 2 hours, got {fires}"


def test_when_a_session_appears_then_event_is_fired_immediately():
  # Arrange
  current = datetime.fromisoformat("2026-08-04T12:00:00+00:00")
  hass = build_hass([])
  result, _ = run(hass, current, None)

  # Act - a session lands in the history a minute later
  hass.data[DOMAIN][ACCOUNT_ID][DATA_FREE_ELECTRICITY_SESSIONS_HISTORY.format(ACCOUNT_ID)] = [
    session("sunday_saver_20260804",
            datetime.fromisoformat("2026-08-04T18:00:00+00:00"),
            datetime.fromisoformat("2026-08-04T20:00:00+00:00"))
  ]
  result, fired = run(hass, current + timedelta(minutes=1), result)

  # Assert - not made to wait for the heartbeat
  assert len(fired) == 1
  assert len(fired[0]["events"]) == 1
  assert fired[0]["events"][0]["code"] == "sunday_saver_20260804"


def test_when_an_upcoming_session_is_announced_then_event_is_fired_immediately():
  # Arrange
  current = datetime.fromisoformat("2026-08-04T12:00:00+00:00")
  hass = build_hass([])
  result, _ = run(hass, current, None)

  # Act - the provider starts reporting a window for tomorrow
  hass.data[DOMAIN][ACCOUNT_ID][DATA_SUNDAY_SAVER.format(ACCOUNT_ID)] = sunday_saver_result(
    "2026-08-05T18:00:00+00:00", "2026-08-05T20:00:00+00:00"
  )
  result, fired = run(hass, current + timedelta(minutes=1), result)

  # Assert - fired straight away rather than waiting for the heartbeat
  assert len(fired) == 1
  assert len(fired[0]["free_electricity_windows"]) == 1
  assert fired[0]["free_electricity_windows"][0]["code"] == "sunday_saver_20260805"


def test_when_only_the_history_changes_then_event_is_still_fired():
  """The panel's history card is driven by free_electricity_windows, so a change confined to the
  retained history has to reach the entity even when today's events are untouched.

  The 60 day purge is the case that does this - it drops an old window without affecting today.
  The existing result is built by hand so the heartbeat is not due, isolating change detection."""
  # Arrange - a window old enough to fall outside retention at `current`
  current = datetime.fromisoformat("2026-08-04T12:00:00+00:00")
  old_session = session("sunday_saver_20260601",
                        datetime.fromisoformat("2026-06-01T18:00:00+00:00"),
                        datetime.fromisoformat("2026-06-01T20:00:00+00:00"))
  hass = build_hass([old_session])
  # Today's events are empty both before and after, and next_refresh is an hour out
  existing_result = FreeElectricitySessionsCoordinatorResult(current, 1, [], False, False)

  # Act
  result, fired = run(hass, current, existing_result)

  # Assert - the purge alone was enough to fire
  assert current < existing_result.next_refresh, "heartbeat must not be due, or this proves nothing"
  assert len(fired) == 1
  assert fired[0]["events"] == []
  assert fired[0]["free_electricity_windows"] == []


def test_when_new_session_appears_then_new_session_event_still_fires():
  """The per-session event is separate from the all-sessions event and must be unaffected."""
  # Arrange
  current = datetime.fromisoformat("2026-08-04T12:00:00+00:00")
  hass = build_hass([
    session("sunday_saver_20260804",
            datetime.fromisoformat("2026-08-04T18:00:00+00:00"),
            datetime.fromisoformat("2026-08-04T20:00:00+00:00"))
  ])
  new_session_events = []

  def fire_event(event_type, payload):
    if event_type == EVENT_NEW_FREE_ELECTRICITY_SESSION:
      new_session_events.append(payload)

  # Act
  refresh_free_electricity_sessions(current, hass, ACCOUNT_ID, None, fire_event)

  # Assert
  assert len(new_session_events) == 1
  assert new_session_events[0]["event_code"] == "sunday_saver_20260804"
