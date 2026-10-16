"""Merging off-peak windows into the stored 60 day history.

The history is what the panel and the card draw their off-peak window lists from, and it
is accumulated from the rates as they refresh. Rates for a window that has not started yet
are a forecast - a smart charging plan lands in them the moment EDF publish it, and EDF
revoke and reshape plans through the day (issue #49). So the merge has to be able to take
a window back out again, while never losing a window that actually ran.
"""
import pytest
from datetime import datetime, timedelta, timezone

from custom_components.edf_energy.storage.off_peak_history import (
  OffPeakWindowRecord,
  merge_off_peak_windows,
)

NOW = datetime(2026, 10, 15, 11, 0, tzinfo=timezone.utc)
DAY_START = NOW.replace(hour=0, minute=0)
DAY_END = DAY_START + timedelta(days=1)

def window(start_hour, end_hour, is_intelligent_adjusted=True, day_offset=0):
  start = DAY_START + timedelta(days=day_offset, hours=start_hour)
  end = DAY_START + timedelta(days=day_offset, hours=end_hour)
  return OffPeakWindowRecord(start, end, is_intelligent_adjusted)

def shape(windows):
  """(start hour, end hour, adjusted) per window, which is all these tests care about."""
  return [
    (int((w.start - DAY_START).total_seconds() // 3600),
     int((w.end - DAY_START).total_seconds() // 3600),
     w.is_intelligent_adjusted)
    for w in windows
  ]

# ── Issue #49: a plan that no longer stands ───────────────────────────────────

def test_when_a_planned_window_is_revoked_then_it_is_removed():
  # Arrange - the overnight window plus a smart charge EDF planned for this afternoon
  history = merge_off_peak_windows([], [window(0, 5, False), window(13, 15)], NOW,
                                   DAY_START, DAY_END)
  assert shape(history) == [(0, 5, False), (13, 15, True)]

  # Act - EDF revoke it and plan the evening instead, so the rates carry only the new one
  history = merge_off_peak_windows(history, [window(0, 5, False), window(18, 20)], NOW,
                                   DAY_START, DAY_END)

  # Assert
  assert shape(history) == [(0, 5, False), (18, 20, True)]

def test_when_a_planned_window_is_reshaped_then_the_old_shape_does_not_remain():
  """Dedup is on the exact start and end, so an extended window used to appear twice."""
  # Arrange
  history = merge_off_peak_windows([], [window(13, 15)], NOW, DAY_START, DAY_END)

  # Act - the same dispatch, half an hour longer
  history = merge_off_peak_windows(history, [window(13, 16)], NOW, DAY_START, DAY_END)

  # Assert
  assert shape(history) == [(13, 16, True)]

def test_when_every_planned_window_is_revoked_then_none_are_left_behind():
  """A day of churn like the one reported left a pile of overlapping windows."""
  # Arrange
  history = []
  for end in (14, 15, 16):
    history = merge_off_peak_windows(history, [window(0, 5, False), window(13, end)], NOW,
                                     DAY_START, DAY_END)

  # Act - the car is unplugged and nothing is planned any more
  history = merge_off_peak_windows(history, [window(0, 5, False)], NOW, DAY_START, DAY_END)

  # Assert
  assert shape(history) == [(0, 5, False)]

# ── What must never be dropped ────────────────────────────────────────────────

def test_when_a_window_has_already_started_then_it_is_kept():
  """It ran, so it is history - even once the rates stop mentioning it."""
  # Arrange - 09:00 to 10:00 is in the past at 11:00
  existing = [window(0, 5, False), window(9, 10)]

  # Act
  history = merge_off_peak_windows(existing, [window(0, 5, False)], NOW, DAY_START, DAY_END)

  # Assert
  assert shape(history) == [(0, 5, False), (9, 10, True)]

def test_when_a_window_is_running_right_now_then_it_is_kept():
  """A dispatch revoked mid-window keeps its shape; the part before the revocation ran."""
  # Arrange - 10:30 to 12:00 spans 11:00
  running = OffPeakWindowRecord(DAY_START + timedelta(hours=10, minutes=30),
                                DAY_START + timedelta(hours=12), True)

  # Act
  history = merge_off_peak_windows([running], [], NOW, DAY_START, DAY_END)

  # Assert
  assert len(history) == 1
  assert history[0].start == running.start and history[0].end == running.end

def test_when_the_rates_do_not_reach_a_future_window_then_it_is_kept():
  """A refresh holding only today must not read as tomorrow's windows being revoked."""
  # Arrange - tomorrow's overnight window, with only today's rates to merge
  existing = [window(0, 5, False), window(1, 6, False, day_offset=1)]

  # Act
  history = merge_off_peak_windows(existing, [window(0, 5, False)], NOW, DAY_START, DAY_END)

  # Assert
  assert shape(history) == [(0, 5, False), (25, 30, False)]

def test_when_no_span_is_given_then_nothing_is_dropped():
  """The old behaviour, for any caller that cannot say what the rates covered."""
  # Arrange
  existing = [window(13, 15)]

  # Act
  history = merge_off_peak_windows(existing, [window(18, 20)], NOW)

  # Assert
  assert shape(history) == [(13, 15, True), (18, 20, True)]

# ── The behaviour that was already there ──────────────────────────────────────

def test_when_windows_are_older_than_sixty_days_then_they_are_purged():
  # Arrange
  old = OffPeakWindowRecord(NOW - timedelta(days=61), NOW - timedelta(days=61, hours=-5), False)

  # Act
  history = merge_off_peak_windows([old, window(0, 5, False)], [], NOW, DAY_START, DAY_END)

  # Assert
  assert shape(history) == [(0, 5, False)]

def test_when_the_same_window_is_merged_twice_then_it_is_not_duplicated():
  # Arrange/Act
  history = merge_off_peak_windows([window(0, 5, False)], [window(0, 5, False)], NOW,
                                   DAY_START, DAY_END)

  # Assert
  assert shape(history) == [(0, 5, False)]

def test_when_a_record_clashes_then_the_intelligent_adjusted_one_wins():
  """Same window, one knowing it was extended by smart charging and one not."""
  # Arrange/Act
  history = merge_off_peak_windows([window(0, 5, False)], [window(0, 5, True)], NOW,
                                   DAY_START, DAY_END)

  # Assert
  assert shape(history) == [(0, 5, True)]

def test_when_windows_arrive_out_of_order_then_they_are_sorted():
  # Arrange - the existing record is one that already ran, so it survives the merge and
  # has to be sorted back into place among the new ones
  history = merge_off_peak_windows([window(9, 10)], [window(0, 5, False), window(13, 15)],
                                   NOW, DAY_START, DAY_END)

  # Assert
  assert shape(history) == [(0, 5, False), (9, 10, True), (13, 15, True)]
