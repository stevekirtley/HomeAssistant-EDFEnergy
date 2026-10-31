"""Telling a day we failed to import from a day EDF never had."""
from datetime import datetime, timedelta
import pytest

from homeassistant.util.dt import (
  DEFAULT_TIME_ZONE,
  get_time_zone,
  set_default_time_zone,
)

from custom_components.edfenergy_uk.statistics.gaps import (
  GAP_FILLABLE,
  GAP_MISSING_AT_SOURCE,
  GAP_PARTIAL_AT_SOURCE,
  assess_gap,
  assess_statistic_gap,
  days_to_report,
  is_old_enough_to_chase,
)

MINIMUM_AGE = timedelta(hours=72)

@pytest.fixture(autouse=True)
def british_time():
  original = DEFAULT_TIME_ZONE
  set_default_time_zone(get_time_zone("Europe/London"))
  yield
  set_default_time_zone(original)

def day(value: str):
  return datetime.fromisoformat(value).date()

def at(value: str) -> datetime:
  return datetime.fromisoformat(value).replace(tzinfo=get_time_zone("Europe/London"))

def test_when_edf_hold_the_whole_day_then_it_is_ours_to_fix():
  result = assess_gap(day("2026-10-20"), 48, 48)

  assert result.status == GAP_FILLABLE
  assert result.hours_missing == 0

def test_when_edf_hold_a_whole_clock_change_day_then_it_is_ours_to_fix():
  result = assess_gap(day("2026-10-25"), 50, 50)

  assert result.status == GAP_FILLABLE

def test_when_edf_hold_nothing_then_the_day_is_missing_at_source():
  result = assess_gap(day("2026-10-20"), 48, 0)

  assert result.status == GAP_MISSING_AT_SOURCE
  assert result.hours_missing == 24

def test_when_edf_hold_some_of_the_day_then_it_is_partial_at_source():
  result = assess_gap(day("2026-10-20"), 48, 40)

  assert result.status == GAP_PARTIAL_AT_SOURCE
  assert result.hours_missing == 4

def test_when_an_odd_number_of_half_hours_is_missing_then_hours_round_up():
  """Someone chasing EDF over ninety minutes should be told two hours, not one."""
  result = assess_gap(day("2026-10-20"), 48, 45)

  assert result.hours_missing == 2

def test_when_the_clocks_change_and_edf_are_short_then_the_longer_day_is_measured():
  result = assess_gap(day("2026-10-25"), 50, 48)

  assert result.status == GAP_PARTIAL_AT_SOURCE
  assert result.hours_missing == 1

@pytest.mark.parametrize("current,expected",[
  # The day ends at midnight on the 21st, so 72 hours later is midnight on the 24th
  ("2026-10-23T23:00:00", False),
  ("2026-10-24T00:00:00", True),
  ("2026-10-30T09:00:00", True),
])
def test_when_a_day_is_recent_then_it_is_not_worth_chasing(current: str, expected: bool):
  assert is_old_enough_to_chase(day("2026-10-20"), at(current), MINIMUM_AGE) == expected

def test_when_reporting_then_only_what_edf_are_missing_is_listed_oldest_first():
  assessments = [
    assess_gap(day("2026-10-22"), 48, 0),
    assess_gap(day("2026-10-20"), 48, 48),
    assess_gap(day("2026-10-21"), 48, 30),
  ]

  assert [a.day.isoformat() for a in days_to_report(assessments)] == ["2026-10-21", "2026-10-22"]

def test_when_a_day_is_still_short_after_a_refresh_then_it_is_judged_on_what_is_held():
  from custom_components.edfenergy_uk.statistics.gaps import StatisticGap

  assert assess_statistic_gap(StatisticGap(day("2026-10-25"), 0, 25)).status == GAP_MISSING_AT_SOURCE
  assert assess_statistic_gap(StatisticGap(day("2026-10-25"), 20, 25)).hours_missing == 5
