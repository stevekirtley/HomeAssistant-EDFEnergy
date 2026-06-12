from datetime import datetime, timezone
import pytest

from custom_components.edf_energy.api_client.free_electricity_sessions import FreeElectricitySession
from custom_components.edf_energy.free_electricity import get_next_free_electricity_session_event


def _session(start_str: str, end_str: str, code: str = "test") -> FreeElectricitySession:
  return FreeElectricitySession(
    code,
    datetime.fromisoformat(start_str),
    datetime.fromisoformat(end_str),
    "sunday_saver",
  )


@pytest.mark.asyncio
async def test_when_events_is_none_then_none_is_returned():
  current = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
  result = get_next_free_electricity_session_event(current, None)
  assert result is None


@pytest.mark.asyncio
async def test_when_events_is_empty_then_none_is_returned():
  current = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
  result = get_next_free_electricity_session_event(current, [])
  assert result is None


@pytest.mark.asyncio
async def test_when_all_events_are_in_the_past_then_none_is_returned():
  current = datetime(2024, 1, 8, 12, 0, 0, tzinfo=timezone.utc)
  events = [
    _session("2024-01-01T10:00:00+00:00", "2024-01-01T12:00:00+00:00"),
    _session("2024-01-07T10:00:00+00:00", "2024-01-07T12:00:00+00:00"),
  ]
  result = get_next_free_electricity_session_event(current, events)
  assert result is None


@pytest.mark.asyncio
async def test_when_multiple_future_events_then_earliest_is_returned():
  current = datetime(2024, 1, 1, 9, 0, 0, tzinfo=timezone.utc)
  session_a = _session("2024-01-07T10:00:00+00:00", "2024-01-07T12:00:00+00:00", "a")
  session_b = _session("2024-01-14T10:00:00+00:00", "2024-01-14T12:00:00+00:00", "b")
  result = get_next_free_electricity_session_event(current, [session_b, session_a])
  assert result == session_a


@pytest.mark.asyncio
async def test_when_one_event_is_current_and_one_is_future_then_future_is_returned():
  current = datetime(2024, 1, 1, 11, 0, 0, tzinfo=timezone.utc)
  current_session = _session("2024-01-01T10:00:00+00:00", "2024-01-01T12:00:00+00:00", "current")
  next_session = _session("2024-01-07T10:00:00+00:00", "2024-01-07T12:00:00+00:00", "next")
  result = get_next_free_electricity_session_event(current, [current_session, next_session])
  assert result == next_session


@pytest.mark.asyncio
async def test_when_single_future_event_then_it_is_returned():
  current = datetime(2024, 1, 1, 9, 0, 0, tzinfo=timezone.utc)
  session = _session("2024-01-07T10:00:00+00:00", "2024-01-07T12:00:00+00:00")
  result = get_next_free_electricity_session_event(current, [session])
  assert result == session
