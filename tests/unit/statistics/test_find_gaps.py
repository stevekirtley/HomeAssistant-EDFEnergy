"""Spotting days the imported consumption statistics are short of."""
from datetime import datetime, timedelta
import pytest

from homeassistant.util.dt import (
  DEFAULT_TIME_ZONE,
  as_utc,
  get_time_zone,
  set_default_time_zone,
  start_of_local_day,
)

from custom_components.edfenergy_uk.statistics.gaps import StatisticGap, find_gaps, shift_sums

RETENTION = 90

@pytest.fixture(autouse=True)
def british_time():
  original = DEFAULT_TIME_ZONE
  set_default_time_zone(get_time_zone("Europe/London"))
  yield
  set_default_time_zone(original)

def at(day: str) -> datetime:
  return datetime.fromisoformat(f"{day}T12:00:00").replace(tzinfo=None).astimezone(get_time_zone("Europe/London"))

def rows_for(days: dict):
  """{day: hours held} as statistics_during_period hands them back."""
  rows = []
  running = 0.0
  for day in sorted(days.keys()):
    start = as_utc(start_of_local_day(datetime.fromisoformat(day)))
    for hour in range(days[day]):
      running += 1
      rows.append({"start": (start + timedelta(hours=hour)).timestamp(), "sum": running, "state": 1.0})
  return rows

def test_when_every_day_is_whole_then_no_gaps():
  rows = rows_for({"2026-10-20": 24, "2026-10-21": 24, "2026-10-22": 24})

  assert find_gaps(rows, at("2026-10-23"), RETENTION) == []

def test_when_a_day_is_missing_then_it_is_reported():
  rows = rows_for({"2026-10-20": 24, "2026-10-22": 24})

  assert find_gaps(rows, at("2026-10-23"), RETENTION) == [
    StatisticGap(datetime.fromisoformat("2026-10-21").date(), 0, 24)
  ]

def test_when_a_day_is_short_then_it_is_reported():
  rows = rows_for({"2026-10-20": 24, "2026-10-21": 19, "2026-10-22": 24})

  assert find_gaps(rows, at("2026-10-23"), RETENTION) == [
    StatisticGap(datetime.fromisoformat("2026-10-21").date(), 19, 24)
  ]

def test_when_the_clocks_go_back_then_twenty_five_hours_are_expected():
  """The real hole this was written for - a twenty five hour day holding the usual twenty four
  looks whole until you ask how long the day actually was."""
  rows = rows_for({"2026-10-24": 24, "2026-10-25": 24, "2026-10-26": 24})

  assert find_gaps(rows, at("2026-10-27"), RETENTION) == [
    StatisticGap(datetime.fromisoformat("2026-10-25").date(), 24, 25)
  ]

def test_when_the_clocks_go_forward_then_twenty_three_hours_is_whole():
  rows = rows_for({"2026-03-28": 24, "2026-03-29": 23, "2026-03-30": 24})

  assert find_gaps(rows, at("2026-03-31"), RETENTION) == []

def test_when_several_days_are_missing_then_all_are_reported():
  rows = rows_for({"2026-10-18": 24, "2026-10-22": 24})

  assert [gap.day.isoformat() for gap in find_gaps(rows, at("2026-10-23"), RETENTION)] == [
    "2026-10-19", "2026-10-20", "2026-10-21"
  ]

def test_when_the_first_day_is_partial_then_it_is_not_a_gap():
  """History starts whenever the meter was first read, not at midnight."""
  rows = rows_for({"2026-10-20": 7, "2026-10-21": 24, "2026-10-22": 24})

  assert find_gaps(rows, at("2026-10-23"), RETENTION) == []

def test_when_the_last_day_is_partial_then_it_is_not_a_gap():
  """The most recent day is still being published."""
  rows = rows_for({"2026-10-20": 24, "2026-10-21": 24, "2026-10-22": 5})

  assert find_gaps(rows, at("2026-10-23"), RETENTION) == []

def test_when_a_gap_is_older_than_retention_then_it_is_left_alone():
  """Statistics go back further than we are willing to go chasing EDF for."""
  # Arrange - a day on its own back in January, then an unbroken run inside the retention
  # window. The months between the two are missing, and all of that is too old to care about.
  days = {"2026-01-01": 24}
  day = datetime.fromisoformat("2026-07-20").date()
  while day <= datetime.fromisoformat("2026-10-22").date():
    days[day.isoformat()] = 24
    day += timedelta(days=1)

  # Act / Assert
  assert find_gaps(rows_for(days), at("2026-10-23"), RETENTION) == []

def test_when_there_are_no_rows_then_no_gaps():
  assert find_gaps([], at("2026-10-23"), RETENTION) == []
  assert find_gaps(None, at("2026-10-23"), RETENTION) == []

# ── Moving the running total of everything above a filled hole ────────────────

def test_when_sums_are_shifted_then_every_running_total_moves_and_states_do_not():
  rows = rows_for({"2026-10-22": 3})

  shifted = shift_sums(rows, 12.5)

  assert [row["sum"] for row in shifted] == [13.5, 14.5, 15.5]
  assert [row["state"] for row in shifted] == [1.0, 1.0, 1.0]

def test_when_a_row_has_no_sum_then_it_is_left_out():
  rows = rows_for({"2026-10-22": 2})
  rows[0]["sum"] = None

  assert len(shift_sums(rows, 1.0)) == 1
