"""Sunday Saver after the scheme was retired (issue #36).

EDF's weekly endpoint now answers 502 for everyone, and the retry anchors on a fixed
timestamp, so a fresh install logged a pair of warnings every refresh while the backoff
climbed. The coordinator no longer asks for it at all.
"""
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.edf_energy.coordinators import sunday_saver as ss
from custom_components.edf_energy.coordinators.sunday_saver import (
  SundaySaverCoordinatorResult,
  async_refresh_sunday_saver,
)

ACCOUNT_ID = "A-XXXXXX"
NOW = datetime(2026, 10, 3, 12, 0, tzinfo=timezone.utc)


class FakeClient:
  """Records whether the dead weekly endpoint was asked for."""

  def __init__(self, enrolled=None):
    self.weekly_calls = 0
    self._enrolled = enrolled

  async def async_get_sunday_saver(self, account_id, week_start_date):
    self.weekly_calls += 1
    raise AssertionError("the retired weekly endpoint must not be called")

  async def async_get_sunday_saver_enrollment_status(self, account_id):
    return self._enrolled

  async def async_join_sunday_saver(self, account_id):
    return False, False


@pytest.mark.asyncio
async def test_retired_weekly_endpoint_is_not_called():
  client = FakeClient()

  result, newly_enrolled = await async_refresh_sunday_saver(NOW, client, ACCOUNT_ID, None)

  assert client.weekly_calls == 0
  assert newly_enrolled is False
  assert result.has_event is False
  assert result.last_error is None


@pytest.mark.asyncio
async def test_existing_history_is_preserved_rather_than_wiped():
  """The panel draws on these, so a retired scheme must not blank them."""
  start = datetime(2026, 8, 2, 7, 0, tzinfo=timezone.utc)
  end = start + timedelta(hours=16)
  existing = SundaySaverCoordinatorResult(NOW - timedelta(days=1), 1, True, 16.0, start, end)

  result, _ = await async_refresh_sunday_saver(NOW, FakeClient(), ACCOUNT_ID, existing)

  assert result.has_event is True
  assert result.free_hours == 16.0
  assert result.start == start
  assert result.end == end


@pytest.mark.asyncio
async def test_request_attempts_stay_at_one_so_no_backoff_builds_up():
  """A permanent 502 used to inflate the attempt count and spam the log on the way up."""
  result, _ = await async_refresh_sunday_saver(NOW, FakeClient(), ACCOUNT_ID, None)

  assert result.request_attempts == 1
  assert result.next_refresh > NOW


@pytest.mark.asyncio
async def test_enrolment_state_is_still_reported():
  result, _ = await async_refresh_sunday_saver(NOW, FakeClient(enrolled=False), ACCOUNT_ID, None)

  assert result.is_enrolled is False


@pytest.mark.asyncio
async def test_nothing_is_fetched_before_the_next_refresh_is_due():
  existing = SundaySaverCoordinatorResult(NOW, 1, False, 0.0, None, None)

  result, newly_enrolled = await async_refresh_sunday_saver(NOW, FakeClient(), ACCOUNT_ID, existing)

  assert result is existing
  assert newly_enrolled is False


def test_the_switch_is_left_in_place_to_revive_the_scheme():
  """Kept deliberately so EDF reviving Sunday Saver is a one-line change."""
  assert ss.WEEKLY_ENDPOINT_SUPPORTED is False
  assert hasattr(ss.EDFEnergyApiClient, "async_get_sunday_saver")
