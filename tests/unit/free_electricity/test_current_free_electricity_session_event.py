from datetime import datetime, timezone
import pytest

from custom_components.edf_energy.api_client.free_electricity_sessions import FreeElectricitySession
from custom_components.edf_energy.free_electricity import current_free_electricity_session_event


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
  result = current_free_electricity_session_event(current, None)
  assert result is None


@pytest.mark.asyncio
async def test_when_events_is_empty_then_none_is_returned():
  current = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
  result = current_free_electricity_session_event(current, [])
  assert result is None


@pytest.mark.asyncio
async def test_when_current_date_is_before_all_events_then_none_is_returned():
  current = datetime(2024, 1, 1, 9, 0, 0, tzinfo=timezone.utc)
  events = [
    _session("2024-01-01T10:00:00+00:00", "2024-01-01T12:00:00+00:00"),
    _session("2024-01-07T10:00:00+00:00", "2024-01-07T12:00:00+00:00"),
  ]
  result = current_free_electricity_session_event(current, events)
  assert result is None


@pytest.mark.asyncio
async def test_when_current_date_is_after_all_events_then_none_is_returned():
  current = datetime(2024, 1, 8, 12, 0, 0, tzinfo=timezone.utc)
  events = [
    _session("2024-01-01T10:00:00+00:00", "2024-01-01T12:00:00+00:00"),
    _session("2024-01-07T10:00:00+00:00", "2024-01-07T12:00:00+00:00"),
  ]
  result = current_free_electricity_session_event(current, events)
  assert result is None


@pytest.mark.asyncio
async def test_when_current_date_is_during_event_then_event_is_returned():
  current = datetime(2024, 1, 1, 11, 0, 0, tzinfo=timezone.utc)
  session = _session("2024-01-01T10:00:00+00:00", "2024-01-01T12:00:00+00:00")
  events = [
    session,
    _session("2024-01-07T10:00:00+00:00", "2024-01-07T12:00:00+00:00"),
  ]
  result = current_free_electricity_session_event(current, events)
  assert result == session


@pytest.mark.asyncio
async def test_when_current_date_is_at_event_start_then_event_is_returned():
  current = datetime(2024, 1, 1, 10, 0, 0, tzinfo=timezone.utc)
  session = _session("2024-01-01T10:00:00+00:00", "2024-01-01T12:00:00+00:00")
  result = current_free_electricity_session_event(current, [session])
  assert result == session


@pytest.mark.asyncio
async def test_when_current_date_is_at_event_end_then_event_is_returned():
  current = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
  session = _session("2024-01-01T10:00:00+00:00", "2024-01-01T12:00:00+00:00")
  result = current_free_electricity_session_event(current, [session])
  assert result == session
