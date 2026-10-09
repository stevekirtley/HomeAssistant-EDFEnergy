"""Working out which days of statistics went missing (issue #42).

The gap arithmetic is what this covers. Whether the import itself works is already
settled by the refresh_previous_consumption_data service, which it hands the date to.
"""
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.edf_energy.statistics.backfill import (
  BACKFILL_MAX_DAYS,
  async_get_first_missing_day,
)

STATISTIC_ID = "electricity_20L1234567_1234567890123_previous_accumulative_consumption"
NOW = datetime(2026, 10, 9, 10, 30, tzinfo=timezone.utc)


@pytest.fixture
def last_statistic(monkeypatch):
  """Stand in for the recorder, which these tests have no need to run."""
  def _set(value):
    async def _fake(hass, statistic_id):
      return value
    monkeypatch.setattr(
      "custom_components.edf_energy.statistics.backfill.async_get_last_statistic_start",
      _fake,
    )
  return _set


@pytest.mark.asyncio
async def test_a_meter_with_no_statistics_is_left_alone(last_statistic):
  """A new install, or statistics the user purged on purpose. Not ours to refill."""
  last_statistic(None)

  assert await async_get_first_missing_day(None, STATISTIC_ID, NOW) is None


@pytest.mark.asyncio
async def test_being_one_day_behind_is_not_a_gap(last_statistic):
  """EDF publish a day or so in arrears, so this is the normal, healthy state."""
  last_statistic(NOW - timedelta(days=1))

  assert await async_get_first_missing_day(None, STATISTIC_ID, NOW) is None


@pytest.mark.asyncio
async def test_up_to_date_statistics_need_nothing(last_statistic):
  last_statistic(NOW)

  assert await async_get_first_missing_day(None, STATISTIC_ID, NOW) is None


@pytest.mark.asyncio
async def test_a_three_day_absence_starts_from_the_first_missing_day(last_statistic):
  """The reported case: Home Assistant off over a weekend.

  Statistics stop on the 5th, so the 6th is the first day missing - not the 5th, which is
  already written, and not the 8th, which is as far as the import will run.
  """
  last_statistic(datetime(2026, 10, 5, 23, 0, tzinfo=timezone.utc))

  assert await async_get_first_missing_day(None, STATISTIC_ID, NOW) == "2026-10-06"


@pytest.mark.asyncio
async def test_a_two_day_gap_is_the_smallest_worth_filling(last_statistic):
  last_statistic(datetime(2026, 10, 6, 23, 0, tzinfo=timezone.utc))

  assert await async_get_first_missing_day(None, STATISTIC_ID, NOW) == "2026-10-07"


@pytest.mark.asyncio
async def test_a_long_absence_is_capped_at_the_most_recent_days(last_statistic):
  """A year off doesn't become 365 days of API calls on one startup.

  The window sits against the end of the gap, so the days nearest the present - the ones
  the dashboard actually shows - are filled first, and the next restart goes further back.
  """
  last_statistic(datetime(2025, 1, 1, tzinfo=timezone.utc))

  first_missing = await async_get_first_missing_day(None, STATISTIC_ID, NOW)

  assert first_missing == (NOW.date() - timedelta(days=BACKFILL_MAX_DAYS)).strftime("%Y-%m-%d")


@pytest.mark.asyncio
async def test_the_cap_is_adjustable(last_statistic):
  last_statistic(datetime(2025, 1, 1, tzinfo=timezone.utc))

  assert await async_get_first_missing_day(None, STATISTIC_ID, NOW, max_days=3) == "2026-10-06"


@pytest.mark.asyncio
async def test_a_gap_inside_the_cap_is_not_shortened(last_statistic):
  """Exactly at the limit: the whole gap still gets filled, nothing is trimmed."""
  last_statistic(NOW - timedelta(days=BACKFILL_MAX_DAYS))

  assert await async_get_first_missing_day(None, STATISTIC_ID, NOW) == (
    (NOW.date() - timedelta(days=BACKFILL_MAX_DAYS - 1)).strftime("%Y-%m-%d")
  )
