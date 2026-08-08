import json
from datetime import datetime, timedelta

from custom_components.edf_energy.api_client.intelligent_dispatches import IntelligentDispatchItem, IntelligentDispatches, SimpleIntelligentDispatchItem
from custom_components.edf_energy.const import CONFIG_DEFAULT_INTELLIGENT_DISPATCH_HISTORY_RETENTION_IN_DAYS
from custom_components.edf_energy.intelligent import clean_intelligent_dispatch_history, summarise_dispatches_for_history
from custom_components.edf_energy.storage.intelligent_dispatches_history import IntelligentDispatchesHistory, IntelligentDispatchesHistoryItem


def build_dispatch(start: datetime, source: str = "smart-charge"):
  return IntelligentDispatchItem(start, start + timedelta(minutes=30), 1.5, source, "AT_HOME")


def build_dispatches(current: datetime, completed_count: int = 0, planned_count: int = 1):
  completed = [build_dispatch(current - timedelta(hours=index + 1)) for index in range(completed_count)]
  planned = [build_dispatch(current + timedelta(hours=index + 1)) for index in range(planned_count)]
  return IntelligentDispatches("SMART_CONTROL_CAPABLE", planned, completed, [])


def test_when_dispatches_provided_then_completed_dispatches_are_not_stored():
  # Arrange
  current = datetime.fromisoformat("2025-10-01T12:00:00+00:00")
  dispatches = build_dispatches(current, completed_count=500, planned_count=2)

  # Act
  result = clean_intelligent_dispatch_history(current, dispatches, [])

  # Assert - completed is the term that made the store grow quadratically
  assert len(result) == 1
  assert result[0].dispatches.completed == []
  assert len(result[0].dispatches.planned) == 2
  assert result[0].dispatches.current_state == "SMART_CONTROL_CAPABLE"
  # The caller's dispatches must not be mutated - the panel still needs completed
  assert len(dispatches.completed) == 500


def test_when_legacy_entries_are_retained_then_their_completed_dispatches_are_dropped():
  """Entries written before 18.9.7 carry a full completed list. Purging by retention isn't enough
  on its own - anything still inside the window keeps that list, so a recovering file stays far
  bigger than it needs to be until those entries age out."""
  # Arrange - legacy shaped entries, all well inside the retention window
  current = datetime.fromisoformat("2025-10-01T12:00:00+00:00")
  history = [
    IntelligentDispatchesHistoryItem(
      current - timedelta(hours=hours),
      build_dispatches(current, completed_count=200, planned_count=hours)
    )
    for hours in range(24, 0, -1)
  ]

  # Act
  result = clean_intelligent_dispatch_history(current, build_dispatches(current, planned_count=99), history, 7)

  # Assert - retained, but normalised on the way through
  assert len(result) == 25
  assert all(item.dispatches.completed == [] for item in result)
  # The rest of each entry is untouched, so the history stays useful
  assert result[0].dispatches.current_state == "SMART_CONTROL_CAPABLE"
  assert len(result[0].dispatches.planned) == 24


def test_when_history_older_than_retention_then_it_is_purged():
  # Arrange
  current = datetime.fromisoformat("2025-10-01T12:00:00+00:00")
  retention_in_days = 7
  history = [
    IntelligentDispatchesHistoryItem(current - timedelta(days=days), build_dispatches(current))
    for days in range(30, 0, -1)
  ]

  # Act
  result = clean_intelligent_dispatch_history(current, build_dispatches(current), history, retention_in_days)

  # Assert - everything within retention, plus one record either side of the boundary
  min_time = current - timedelta(days=retention_in_days)
  assert len([item for item in result if item.timestamp < min_time]) <= 1
  assert len(result) <= retention_in_days + 2


def test_when_retention_is_configured_then_it_is_honoured():
  # Arrange - vary the dispatches so every entry is genuinely distinct
  current = datetime.fromisoformat("2025-10-01T12:00:00+00:00")
  history = [
    IntelligentDispatchesHistoryItem(current - timedelta(days=days), build_dispatches(current, planned_count=days))
    for days in range(59, 0, -1)
  ]

  # Act
  # planned_count differs from the newest stored entry, so a new entry is genuinely added
  short = clean_intelligent_dispatch_history(current, build_dispatches(current, planned_count=3), list(history), 2)
  long = clean_intelligent_dispatch_history(current, build_dispatches(current, planned_count=3), list(history), 60)

  # Assert
  assert len(short) < len(long)
  # 59 stored entries all fall inside a 60 day window, plus the new entry for `current`
  assert len(long) == 60
  # The 1 and 2 day old entries (2 days sits exactly on the boundary), plus the one record kept
  # from just before it, plus the new entry
  assert len(short) == 4


def test_when_max_entries_exceeded_then_oldest_entries_are_dropped():
  # Arrange - vary the dispatches so nothing is deduped away
  current = datetime.fromisoformat("2025-10-01T12:00:00+00:00")
  history = [
    IntelligentDispatchesHistoryItem(current - timedelta(minutes=index), build_dispatches(current, planned_count=index))
    for index in range(500, 0, -1)
  ]

  # Act
  result = clean_intelligent_dispatch_history(current, build_dispatches(current, planned_count=3), history, 60, 100)

  # Assert - capped, and it is the newest entries that survive
  assert len(result) == 100
  assert result[-1].timestamp == current
  assert result[0].timestamp == current - timedelta(minutes=99)


def test_when_dispatches_unchanged_then_no_new_entry_is_added():
  # Arrange
  current = datetime.fromisoformat("2025-10-01T12:00:00+00:00")
  dispatches = build_dispatches(current)
  history = [IntelligentDispatchesHistoryItem(current - timedelta(minutes=3), summarise_dispatches_for_history(dispatches))]

  # Act
  result = clean_intelligent_dispatch_history(current, dispatches, history)

  # Assert
  assert len(result) == 1


def test_when_only_completed_dispatches_change_then_no_new_entry_is_added():
  """Completed dispatches accumulate constantly but are not stored, so they must not
  trigger a new history entry on every poll."""
  # Arrange
  current = datetime.fromisoformat("2025-10-01T12:00:00+00:00")
  first = build_dispatches(current, completed_count=10)
  second = build_dispatches(current, completed_count=40)

  # Act
  history = clean_intelligent_dispatch_history(current, first, [])
  result = clean_intelligent_dispatch_history(current + timedelta(minutes=3), second, history)

  # Assert
  assert len(result) == 1


def test_when_dispatches_change_every_poll_then_store_stays_bounded():
  """Regression test for the runaway .storage file that pushed users into OOM.

  Simulates 60 days of dispatches changing on every 3 minute poll, with a full retention
  window of completed dispatches present each time."""
  # Arrange
  current = datetime.fromisoformat("2025-10-01T12:00:00+00:00")
  history = []
  polls = (60 * 24 * 60) // 3

  # Act - step in 3 minute increments, changing the planned dispatches each time
  for index in range(polls):
    time = current + timedelta(minutes=3 * index)
    dispatches = IntelligentDispatches(
      "SMART_CONTROL_CAPABLE",
      [build_dispatch(time + timedelta(minutes=index % 120))],
      [build_dispatch(time - timedelta(hours=hour)) for hour in range(1, 100)],
      [SimpleIntelligentDispatchItem(time, time + timedelta(minutes=30))]
    )
    history = clean_intelligent_dispatch_history(time, dispatches, history, CONFIG_DEFAULT_INTELLIGENT_DISPATCH_HISTORY_RETENTION_IN_DAYS)

  # Assert
  serialised = json.dumps(IntelligentDispatchesHistory(history).to_dict(), default=str)
  size_in_mb = len(serialised) / (1024 * 1024)

  assert len(history) <= 5000, f"history grew to {len(history)} entries"
  assert size_in_mb < 5, f"history serialised to {size_in_mb:.1f}MB"
  assert all(item.dispatches.completed == [] for item in history)
