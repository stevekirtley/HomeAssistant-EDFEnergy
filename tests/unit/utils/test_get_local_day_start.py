"""The boundaries a day of consumption is asked for between.

A day is a local day. Asking EDF for twenty four hours from midnight UTC is an hour out all
through British Summer Time, and on the day the clocks go back it is an hour short - which is
how the hole the backfill exists to fill came to be there, and why filling it left the first
hour of the day still missing.
"""
from datetime import date, timedelta
import pytest

from homeassistant.util.dt import (
  DEFAULT_TIME_ZONE,
  get_time_zone,
  set_default_time_zone,
)

from custom_components.edfenergy_uk.utils import get_local_day_start

@pytest.fixture(autouse=True)
def british_time():
  """The test box runs in UTC, so the clock change is invisible without this."""
  original = DEFAULT_TIME_ZONE
  set_default_time_zone(get_time_zone("Europe/London"))
  yield
  set_default_time_zone(original)

def hours_in(day: str) -> float:
  """What the refresh asks EDF for: this day's midnight to the next day's."""
  start = date.fromisoformat(day)
  span = get_local_day_start(start + timedelta(days=1)) - get_local_day_start(start)
  return span.total_seconds() / 3600

def test_a_winter_day_starts_at_midnight_utc():
  assert get_local_day_start(date(2026, 1, 15)).isoformat() == "2026-01-15T00:00:00+00:00"

def test_a_summer_day_starts_an_hour_before_midnight_utc():
  """Where stepping in UTC went wrong - British Summer Time midnight is 23:00 the day before."""
  assert get_local_day_start(date(2026, 7, 15)).isoformat() == "2026-07-14T23:00:00+00:00"

def test_the_day_the_clocks_go_back_is_asked_for_as_twenty_five_hours():
  assert hours_in("2026-10-25") == 25

def test_the_day_the_clocks_go_forward_is_asked_for_as_twenty_three_hours():
  assert hours_in("2026-03-29") == 23

def test_an_ordinary_day_is_asked_for_as_twenty_four_hours():
  assert hours_in("2026-07-15") == 24
  assert hours_in("2026-01-15") == 24

def test_a_datetime_is_taken_as_the_day_it_falls_on():
  """The refresh hands dates around, but callers elsewhere hold datetimes."""
  from datetime import datetime
  midday = datetime(2026, 10, 25, 12, 30)
  assert get_local_day_start(midday) == get_local_day_start(date(2026, 10, 25))

def test_consecutive_days_meet_exactly():
  """No gap and no overlap across the clock change, or an hour is imported twice or not at all."""
  day = date(2026, 10, 23)
  for _ in range(5):
    assert get_local_day_start(day + timedelta(days=1)) == get_local_day_start(day) + timedelta(
      hours=hours_in(day.isoformat()))
    day = day + timedelta(days=1)
