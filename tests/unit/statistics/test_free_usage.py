from datetime import datetime, timedelta

import pytest
from homeassistant.util.dt import parse_datetime

from custom_components.edfenergy_uk.statistics.free_usage import (
  estimate_from_rows,
  overlap_in_hours,
)


def hours(start: str, count: int, each: float):
  """`count` hourly rows from `start`, each with the same consumption."""
  begin = parse_datetime(start)
  return [
    {"start": begin + timedelta(hours=i), "change": each}
    for i in range(count)
  ]


def window(start: str, end: str):
  return (parse_datetime(start), parse_datetime(end))


@pytest.mark.asyncio
async def test_when_no_sessions_then_nothing_is_estimated():
  rows = hours("2026-09-28T00:00:00+01:00", 24, 1.0)
  result = estimate_from_rows(rows, [], parse_datetime("2026-09-28T00:00:00+01:00"),
                              parse_datetime("2026-09-29T00:00:00+01:00"))
  assert result.consumption == 0
  assert result.sessions == 0


@pytest.mark.asyncio
async def test_when_session_covers_whole_hours_then_those_hours_are_counted():
  rows = hours("2026-09-28T00:00:00+01:00", 24, 2.0)
  sessions = [window("2026-09-28T02:00:00+01:00", "2026-09-28T05:00:00+01:00")]
  result = estimate_from_rows(rows, sessions, parse_datetime("2026-09-28T00:00:00+01:00"),
                              parse_datetime("2026-09-29T00:00:00+01:00"))
  assert result.consumption == 6.0
  assert result.sessions == 1


@pytest.mark.asyncio
async def test_when_session_covers_half_an_hour_then_half_of_it_is_counted():
  rows = hours("2026-09-28T00:00:00+01:00", 24, 4.0)
  sessions = [window("2026-09-28T02:30:00+01:00", "2026-09-28T03:00:00+01:00")]
  result = estimate_from_rows(rows, sessions, parse_datetime("2026-09-28T00:00:00+01:00"),
                              parse_datetime("2026-09-29T00:00:00+01:00"))
  assert result.consumption == 2.0


@pytest.mark.asyncio
async def test_when_sessions_overlap_then_an_hour_is_not_counted_twice():
  rows = hours("2026-09-28T00:00:00+01:00", 24, 3.0)
  sessions = [
    window("2026-09-28T02:00:00+01:00", "2026-09-28T04:00:00+01:00"),
    window("2026-09-28T03:00:00+01:00", "2026-09-28T05:00:00+01:00"),
  ]
  result = estimate_from_rows(rows, sessions, parse_datetime("2026-09-28T00:00:00+01:00"),
                              parse_datetime("2026-09-29T00:00:00+01:00"))
  # Three distinct hours are covered, not four.
  assert result.consumption == 9.0


@pytest.mark.asyncio
async def test_when_session_is_outside_the_window_then_it_is_ignored():
  rows = hours("2026-09-28T00:00:00+01:00", 24, 1.0)
  sessions = [window("2026-09-20T02:00:00+01:00", "2026-09-20T04:00:00+01:00")]
  result = estimate_from_rows(rows, sessions, parse_datetime("2026-09-28T00:00:00+01:00"),
                              parse_datetime("2026-09-29T00:00:00+01:00"))
  assert result.consumption == 0
  assert result.sessions == 0


@pytest.mark.asyncio
async def test_when_session_runs_past_midnight_then_only_the_window_is_counted():
  rows = hours("2026-09-28T00:00:00+01:00", 24, 2.0)
  sessions = [window("2026-09-27T23:00:00+01:00", "2026-09-28T02:00:00+01:00")]
  result = estimate_from_rows(rows, sessions, parse_datetime("2026-09-28T00:00:00+01:00"),
                              parse_datetime("2026-09-29T00:00:00+01:00"))
  # The 23:00 hour belongs to the previous day and has no row here.
  assert result.consumption == 4.0


@pytest.mark.asyncio
async def test_when_an_hour_has_no_reading_then_it_contributes_nothing():
  rows = hours("2026-09-28T00:00:00+01:00", 24, 2.0)
  rows[3]["change"] = None
  sessions = [window("2026-09-28T02:00:00+01:00", "2026-09-28T05:00:00+01:00")]
  result = estimate_from_rows(rows, sessions, parse_datetime("2026-09-28T00:00:00+01:00"),
                              parse_datetime("2026-09-29T00:00:00+01:00"))
  assert result.consumption == 4.0


@pytest.mark.asyncio
async def test_when_cost_rows_are_given_then_the_credit_is_estimated_too():
  rows = hours("2026-09-28T00:00:00+01:00", 24, 2.0)
  costs = hours("2026-09-28T00:00:00+01:00", 24, 0.55)
  sessions = [window("2026-09-28T02:00:00+01:00", "2026-09-28T05:00:00+01:00")]
  result = estimate_from_rows(rows, sessions, parse_datetime("2026-09-28T00:00:00+01:00"),
                              parse_datetime("2026-09-29T00:00:00+01:00"), cost_rows=costs)
  assert result.consumption == 6.0
  assert result.cost == 1.65


@pytest.mark.asyncio
async def test_when_there_are_no_cost_rows_then_the_credit_is_zero_not_wrong():
  rows = hours("2026-09-28T00:00:00+01:00", 24, 2.0)
  sessions = [window("2026-09-28T02:00:00+01:00", "2026-09-28T05:00:00+01:00")]
  result = estimate_from_rows(rows, sessions, parse_datetime("2026-09-28T00:00:00+01:00"),
                              parse_datetime("2026-09-29T00:00:00+01:00"))
  assert result.consumption == 6.0
  assert result.cost == 0.0


@pytest.mark.asyncio
async def test_overlap_is_zero_when_periods_only_touch():
  a = parse_datetime("2026-09-28T02:00:00+01:00")
  b = parse_datetime("2026-09-28T03:00:00+01:00")
  c = parse_datetime("2026-09-28T04:00:00+01:00")
  assert overlap_in_hours(a, b, b, c) == 0
  assert overlap_in_hours(a, c, b, c) == 1


@pytest.mark.asyncio
async def test_when_the_meter_serial_has_letters_then_the_statistic_is_still_found(monkeypatch):
  """The statistics are written with the id folded down, so asking in the API's own casing
  finds nothing and reads as no usage at all - which is what it did."""
  from custom_components.edfenergy_uk.statistics import free_usage

  asked = {}

  def fake_statistics_during_period(hass, start, end, ids, period, units, types):
    asked["ids"] = set(ids)
    return {next(iter(ids)): hours("2026-09-28T00:00:00+01:00", 24, 2.0)}

  class FakeRecorder:
    async def async_add_executor_job(self, func, *args):
      return func(*args)

  monkeypatch.setattr(free_usage, "statistics_during_period", fake_statistics_during_period)
  monkeypatch.setattr(free_usage, "get_instance", lambda hass: FakeRecorder())

  sessions = [window("2026-09-28T02:00:00+01:00", "2026-09-28T04:00:00+01:00")]
  result = await free_usage.async_estimate_free_usage(
    None,
    "edf_energy:electricity_20L1234567_1234567890123_previous_accumulative_consumption",
    sessions,
    parse_datetime("2026-09-28T00:00:00+01:00"),
    parse_datetime("2026-09-29T00:00:00+01:00"),
  )

  assert asked["ids"] == {
    "edf_energy:electricity_20l1234567_1234567890123_previous_accumulative_consumption"
  }
  assert result.consumption == 4.0
