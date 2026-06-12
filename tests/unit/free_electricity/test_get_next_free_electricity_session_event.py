from datetime import datetime
import pytest

from custom_components.edf_energy.free_electricity import get_next_free_electricity_session_event
from custom_components.edf_energy.api_client.free_electricity_sessions import FreeElectricitySession

@pytest.mark.asyncio
async def test_when_future_events_present_then_next_event_returned():
  events = [
    FreeElectricitySession("1", datetime.strptime("2026-06-06T17:00:00Z", "%Y-%m-%dT%H:%M:%S%z"), datetime.strptime("2026-06-06T18:00:00Z", "%Y-%m-%dT%H:%M:%S%z"), "sunday_saver"),
    FreeElectricitySession("2", datetime.strptime("2026-06-05T17:00:00Z", "%Y-%m-%dT%H:%M:%S%z"), datetime.strptime("2026-06-05T18:00:00Z", "%Y-%m-%dT%H:%M:%S%z"), "football"),
    FreeElectricitySession("3", datetime.strptime("2026-06-07T17:00:00Z", "%Y-%m-%dT%H:%M:%S%z"), datetime.strptime("2026-06-07T18:00:00Z", "%Y-%m-%dT%H:%M:%S%z"), "sunday_saver")
  ]

  current_date = datetime.strptime("2026-06-04T17:00:00Z", "%Y-%m-%dT%H:%M:%S%z")

  result = get_next_free_electricity_session_event(
    current_date,
    events,
  )

  assert result == events[1]
  assert result.duration_in_minutes == 60

@pytest.mark.asyncio
async def test_when_event_is_active_then_subsequent_event_returned():
  events = [
    FreeElectricitySession("1", datetime.strptime("2026-06-06T17:00:00Z", "%Y-%m-%dT%H:%M:%S%z"), datetime.strptime("2026-06-06T18:00:00Z", "%Y-%m-%dT%H:%M:%S%z"), "sunday_saver"),
    FreeElectricitySession("2", datetime.strptime("2026-06-07T17:00:00Z", "%Y-%m-%dT%H:%M:%S%z"), datetime.strptime("2026-06-07T18:00:00Z", "%Y-%m-%dT%H:%M:%S%z"), "football")
  ]

  # Within the first event's window - the "next" event should be the one that has not started yet
  current_date = datetime.strptime("2026-06-06T17:30:00Z", "%Y-%m-%dT%H:%M:%S%z")

  result = get_next_free_electricity_session_event(
    current_date,
    events,
  )

  assert result == events[1]

@pytest.mark.asyncio
async def test_when_no_future_events_present_then_none_returned():
  events = [
    FreeElectricitySession("1", datetime.strptime("2026-06-06T17:00:00Z", "%Y-%m-%dT%H:%M:%S%z"), datetime.strptime("2026-06-06T18:00:00Z", "%Y-%m-%dT%H:%M:%S%z"), "sunday_saver"),
    FreeElectricitySession("2", datetime.strptime("2026-06-05T17:00:00Z", "%Y-%m-%dT%H:%M:%S%z"), datetime.strptime("2026-06-05T18:00:00Z", "%Y-%m-%dT%H:%M:%S%z"), "football"),
    FreeElectricitySession("3", datetime.strptime("2026-06-07T17:00:00Z", "%Y-%m-%dT%H:%M:%S%z"), datetime.strptime("2026-06-07T18:00:00Z", "%Y-%m-%dT%H:%M:%S%z"), "sunday_saver")
  ]

  current_date = datetime.strptime("2026-06-08T17:00:00Z", "%Y-%m-%dT%H:%M:%S%z")

  result = get_next_free_electricity_session_event(
    current_date,
    events,
  )

  assert result is None

@pytest.mark.asyncio
async def test_when_events_is_none_then_none_returned():
  events = None
  current_date = datetime.strptime("2026-06-08T17:00:00Z", "%Y-%m-%dT%H:%M:%S%z")

  result = get_next_free_electricity_session_event(
    current_date,
    events,
  )

  assert result is None
