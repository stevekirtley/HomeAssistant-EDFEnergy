from datetime import datetime
import pytest

from custom_components.edf_energy.free_electricity import current_free_electricity_session_event
from custom_components.edf_energy.api_client.free_electricity_sessions import FreeElectricitySession

@pytest.mark.asyncio
async def test_when_event_is_active_then_event_returned():
  events = [
    FreeElectricitySession("1", datetime.strptime("2026-06-06T17:00:00Z", "%Y-%m-%dT%H:%M:%S%z"), datetime.strptime("2026-06-06T18:00:00Z", "%Y-%m-%dT%H:%M:%S%z"), "sunday_saver"),
    FreeElectricitySession("2", datetime.strptime("2026-06-07T17:00:00Z", "%Y-%m-%dT%H:%M:%S%z"), datetime.strptime("2026-06-07T18:00:00Z", "%Y-%m-%dT%H:%M:%S%z"), "football")
  ]

  current_date = datetime.strptime("2026-06-06T17:30:00Z", "%Y-%m-%dT%H:%M:%S%z")

  result = current_free_electricity_session_event(
    current_date,
    events,
  )

  assert result == events[0]
  assert result.source == "sunday_saver"

@pytest.mark.asyncio
async def test_when_current_date_on_boundary_then_event_returned():
  events = [
    FreeElectricitySession("1", datetime.strptime("2026-06-06T17:00:00Z", "%Y-%m-%dT%H:%M:%S%z"), datetime.strptime("2026-06-06T18:00:00Z", "%Y-%m-%dT%H:%M:%S%z"), "sunday_saver")
  ]

  # Exactly on the start boundary is treated as active
  current_date = datetime.strptime("2026-06-06T17:00:00Z", "%Y-%m-%dT%H:%M:%S%z")

  result = current_free_electricity_session_event(
    current_date,
    events,
  )

  assert result == events[0]

@pytest.mark.asyncio
async def test_when_no_event_active_then_none_returned():
  events = [
    FreeElectricitySession("1", datetime.strptime("2026-06-06T17:00:00Z", "%Y-%m-%dT%H:%M:%S%z"), datetime.strptime("2026-06-06T18:00:00Z", "%Y-%m-%dT%H:%M:%S%z"), "sunday_saver")
  ]

  current_date = datetime.strptime("2026-06-06T19:00:00Z", "%Y-%m-%dT%H:%M:%S%z")

  result = current_free_electricity_session_event(
    current_date,
    events,
  )

  assert result is None

@pytest.mark.asyncio
async def test_when_events_is_none_then_none_returned():
  events = None
  current_date = datetime.strptime("2026-06-06T17:30:00Z", "%Y-%m-%dT%H:%M:%S%z")

  result = current_free_electricity_session_event(
    current_date,
    events,
  )

  assert result is None
