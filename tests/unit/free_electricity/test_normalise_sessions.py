from datetime import datetime
import pytest

from custom_components.edf_energy.coordinators.free_electricity_sessions import (
  _normalise_sunday_saver,
  _normalise_football,
  _merge_sessions,
)
from custom_components.edf_energy.coordinators.sunday_saver import SundaySaverCoordinatorResult
from custom_components.edf_energy.coordinators.event_free_electricity import EventFreeElectricityCoordinatorResult
from custom_components.edf_energy.api_client.free_electricity_sessions import FreeElectricitySession

current = datetime.strptime("2026-06-12T10:00:00Z", "%Y-%m-%dT%H:%M:%S%z")


# ── Sunday Saver normaliser ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_sunday_saver_when_no_result_then_empty():
  assert _normalise_sunday_saver(None) == []

@pytest.mark.asyncio
async def test_sunday_saver_when_no_event_then_empty():
  result = SundaySaverCoordinatorResult(current, 1, False, 0.0, None, None)
  assert _normalise_sunday_saver(result) == []

@pytest.mark.asyncio
async def test_sunday_saver_when_event_missing_end_then_empty():
  start = datetime.strptime("2026-06-14T11:00:00Z", "%Y-%m-%dT%H:%M:%S%z")
  result = SundaySaverCoordinatorResult(current, 1, True, 1.0, start, None)
  assert _normalise_sunday_saver(result) == []

@pytest.mark.asyncio
async def test_sunday_saver_when_event_present_then_single_session():
  start = datetime.strptime("2026-06-14T11:00:00Z", "%Y-%m-%dT%H:%M:%S%z")
  end = datetime.strptime("2026-06-14T12:00:00Z", "%Y-%m-%dT%H:%M:%S%z")
  result = SundaySaverCoordinatorResult(current, 1, True, 1.0, start, end)

  sessions = _normalise_sunday_saver(result)

  assert len(sessions) == 1
  assert sessions[0].source == "sunday_saver"
  assert sessions[0].code == "sunday_saver_20260614"
  assert sessions[0].start == start
  assert sessions[0].end == end
  assert sessions[0].duration_in_minutes == 60


# ── Football normaliser ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_football_when_no_result_then_empty():
  assert _normalise_football(None) == []

@pytest.mark.asyncio
async def test_football_when_no_event_then_empty():
  result = EventFreeElectricityCoordinatorResult(current, 1, None, None, None)
  assert _normalise_football(result) == []

@pytest.mark.asyncio
async def test_football_when_event_present_then_single_session():
  start = datetime.strptime("2026-06-14T13:00:00Z", "%Y-%m-%dT%H:%M:%S%z")
  end = datetime.strptime("2026-06-14T15:00:00Z", "%Y-%m-%dT%H:%M:%S%z")
  result = EventFreeElectricityCoordinatorResult(current, 1, start, end, "Haiti v Scotland")

  sessions = _normalise_football(result)

  assert len(sessions) == 1
  assert sessions[0].source == "football"
  assert sessions[0].code == "football_202606141300"
  assert sessions[0].start == start
  assert sessions[0].end == end
  assert sessions[0].duration_in_minutes == 120


# ── Merge / sort / dedup ───────────────────────────────────────────────────

def _session(code, start_str, end_str, source):
  return FreeElectricitySession(
    code,
    datetime.strptime(start_str, "%Y-%m-%dT%H:%M:%S%z"),
    datetime.strptime(end_str, "%Y-%m-%dT%H:%M:%S%z"),
    source,
  )

@pytest.mark.asyncio
async def test_merge_sorts_by_start():
  football = _session("football_202606141300", "2026-06-14T13:00:00Z", "2026-06-14T15:00:00Z", "football")
  sunday = _session("sunday_saver_20260614", "2026-06-14T11:00:00Z", "2026-06-14T12:00:00Z", "sunday_saver")

  merged = _merge_sessions([football, sunday])

  assert [s.code for s in merged] == ["sunday_saver_20260614", "football_202606141300"]

@pytest.mark.asyncio
async def test_merge_dedups_identical_windows():
  a = _session("sunday_saver_20260614", "2026-06-14T11:00:00Z", "2026-06-14T12:00:00Z", "sunday_saver")
  dup = _session("sunday_saver_20260614", "2026-06-14T11:00:00Z", "2026-06-14T12:00:00Z", "sunday_saver")

  merged = _merge_sessions([a, dup])

  assert len(merged) == 1

@pytest.mark.asyncio
async def test_merge_keeps_overlapping_but_different_windows():
  # Overlapping windows from different sources are both retained - Predbat treats the union
  # as zero rate, so keeping both is harmless and preserves source information.
  sunday = _session("sunday_saver_20260614", "2026-06-14T13:00:00Z", "2026-06-14T14:00:00Z", "sunday_saver")
  football = _session("football_202606141300", "2026-06-14T13:00:00Z", "2026-06-14T15:00:00Z", "football")

  merged = _merge_sessions([sunday, football])

  assert len(merged) == 2

@pytest.mark.asyncio
async def test_merge_when_empty_then_empty():
  assert _merge_sessions([]) == []
