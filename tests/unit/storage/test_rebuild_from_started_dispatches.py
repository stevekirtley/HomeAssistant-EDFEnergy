"""Putting back the smart charging windows 21.0.0 took out of the stored history.

That release clipped the whole sixty days of stored windows on every refresh and saved the
result, so re-planned charges that overlapped each other were dropped or cut short. The
windows are gone from the store, but the started dispatches record what actually charged and
were never touched, so the part of each lost window that ran can be worked out again.

What matters most here is what the repair must not do: take anything away, invent a charge
that never ran, or reach into time the rates still own.
"""
from datetime import datetime, timedelta, timezone

from custom_components.edfenergy_uk.api_client.intelligent_dispatches import SimpleIntelligentDispatchItem
from custom_components.edfenergy_uk.storage.off_peak_history import (
  OffPeakWindowRecord,
  rebuild_from_started_dispatches,
)

TODAY = datetime(2026, 11, 5, 0, 0, tzinfo=timezone.utc)
DAY = TODAY - timedelta(days=10)

def at(hour, day=DAY):
  return day + timedelta(hours=hour)

def window(start_hour, end_hour, smart=True, day=DAY):
  return OffPeakWindowRecord(at(start_hour, day), at(end_hour, day), smart)

def ran(start_hour, end_hour, day=DAY):
  return SimpleIntelligentDispatchItem(at(start_hour, day), at(end_hour, day))

def shape(windows, day=DAY):
  return [((w.start - day).total_seconds() / 3600, (w.end - day).total_seconds() / 3600, w.is_intelligent_adjusted)
          for w in windows]

def test_when_a_charge_that_ran_was_cut_short_then_the_rest_comes_back():
  """The reported case: a charge that ran 05:00 to 11:30 had been clipped to 05:00 to 07:00."""
  # Arrange
  history = [window(0, 5, smart=False), window(5, 7)]

  # Act
  rebuilt, added = rebuild_from_started_dispatches(history, [ran(5, 11.5)], TODAY)

  # Assert
  assert added == 1
  assert shape(rebuilt) == [(0, 5, False), (5, 7, True), (7, 11.5, True)]

def test_when_a_window_was_planned_but_never_ran_then_it_is_not_put_back():
  """A plan EDF revoked never happened, so there is no dispatch for it and nothing to add."""
  # Arrange - the store has the overnight window only, and the only dispatch is elsewhere
  history = [window(0, 5, smart=False)]

  # Act
  rebuilt, added = rebuild_from_started_dispatches(history, [], TODAY)

  # Assert
  assert added == 0
  assert shape(rebuilt) == [(0, 5, False)]

def test_when_a_dispatch_runs_through_the_standard_window_then_that_part_is_not_doubled():
  """Smart charging inside the normal off peak hours is already shown as the standard window."""
  # Arrange
  history = [window(0, 5, smart=False)]

  # Act - a charge from 03:00 to 08:00, two hours of it inside the standard window
  rebuilt, added = rebuild_from_started_dispatches(history, [ran(3, 8)], TODAY)

  # Assert
  assert shape(rebuilt) == [(0, 5, False), (5, 8, True)]

def test_nothing_already_stored_is_changed_or_removed():
  """Only ever adds - including overlapping records from before #49 was fixed."""
  # Arrange
  history = [window(0, 5, smart=False), window(5, 10), window(5, 14), window(20, 21)]
  before = shape(history)

  # Act
  rebuilt, _ = rebuild_from_started_dispatches(history, [ran(5, 16), ran(22, 23)], TODAY)

  # Assert - every original record is still there exactly as it was
  for record in before:
    assert record in shape(rebuilt)

def test_today_is_left_to_the_rates():
  """The rates still cover today and tomorrow, and they are what decide those windows."""
  # Arrange
  history = [window(0, 5, smart=False, day=TODAY - timedelta(days=1))]

  # Act - a dispatch running from yesterday evening into this morning
  rebuilt, _ = rebuild_from_started_dispatches(
    history, [ran(21, 30, day=TODAY - timedelta(days=1))], TODAY)

  # Assert - added up to midnight and no further
  assert max(w.end for w in rebuilt) == TODAY

def test_nothing_is_added_from_before_the_history_began():
  """A sensor that started recording recently must not suddenly gain weeks it never saw."""
  # Arrange - the history starts on DAY, but dispatches go back further
  history = [window(0, 5, smart=False)]
  older = ran(10, 12, day=DAY - timedelta(days=7))

  # Act
  rebuilt, added = rebuild_from_started_dispatches(history, [older], TODAY)

  # Assert
  assert added == 0
  assert min(w.start for w in rebuilt) == DAY

def test_running_it_twice_adds_nothing_the_second_time():
  """It is recorded as done, but if that record were ever lost it must still be harmless."""
  # Arrange
  history = [window(0, 5, smart=False), window(5, 7)]
  once, first = rebuild_from_started_dispatches(history, [ran(5, 11.5)], TODAY)

  # Act
  twice, second = rebuild_from_started_dispatches(once, [ran(5, 11.5)], TODAY)

  # Assert
  assert first == 1 and second == 0
  assert shape(twice) == shape(once)

def test_with_no_history_or_no_dispatches_nothing_happens():
  assert rebuild_from_started_dispatches([], [ran(5, 7)], TODAY) == ([], 0)

  history = [window(0, 5, smart=False)]
  assert rebuild_from_started_dispatches(history, [], TODAY) == (history, 0)
