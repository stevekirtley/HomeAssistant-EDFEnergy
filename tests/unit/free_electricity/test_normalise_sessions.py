from datetime import datetime, timezone, timedelta
import pytest

from custom_components.edf_energy.api_client.free_electricity_sessions import FreeElectricitySession
from custom_components.edf_energy.coordinators.free_electricity_sessions import (
  _normalise_sunday_saver,
  _normalise_football,
  _merge_sessions,
  _sessions_equal,
)


def _make_result(has_event, start_str=None, end_str=None):
  """Minimal stub for SundaySaverCoordinatorResult / EventFreeElectricityCoordinatorResult."""
  class _Stub:
    pass
  r = _Stub()
  r.has_event = has_event
  r.start = datetime.fromisoformat(start_str) if start_str else None
  r.end = datetime.fromisoformat(end_str) if end_str else None
  return r


def _session(start_str, end_str, code="test", source="sunday_saver"):
  return FreeElectricitySession(code, datetime.fromisoformat(start_str), datetime.fromisoformat(end_str), source)


# ── _normalise_sunday_saver ────────────────────────────────────────────────────

class TestNormaliseSundaySaver:
  def test_when_result_is_none_then_empty_list_returned(self):
    assert _normalise_sunday_saver(None) == []

  def test_when_has_event_is_false_then_empty_list_returned(self):
    result = _make_result(False, "2024-01-07T10:00:00+00:00", "2024-01-07T12:00:00+00:00")
    assert _normalise_sunday_saver(result) == []

  def test_when_start_is_none_then_empty_list_returned(self):
    result = _make_result(True, None, "2024-01-07T12:00:00+00:00")
    assert _normalise_sunday_saver(result) == []

  def test_when_end_is_none_then_empty_list_returned(self):
    result = _make_result(True, "2024-01-07T10:00:00+00:00", None)
    assert _normalise_sunday_saver(result) == []

  def test_when_valid_result_then_session_is_returned(self):
    result = _make_result(True, "2024-01-07T10:00:00+00:00", "2024-01-07T12:00:00+00:00")
    sessions = _normalise_sunday_saver(result)
    assert len(sessions) == 1
    assert sessions[0].source == "sunday_saver"
    assert sessions[0].code == "sunday_saver_20240107"
    assert sessions[0].duration_in_minutes == 120


# ── _normalise_football ────────────────────────────────────────────────────────

class TestNormaliseFootball:
  def test_when_result_is_none_then_empty_list_returned(self):
    assert _normalise_football(None) == []

  def test_when_has_event_is_false_then_empty_list_returned(self):
    result = _make_result(False, "2026-06-15T18:00:00+00:00", "2026-06-15T20:00:00+00:00")
    assert _normalise_football(result) == []

  def test_when_valid_result_then_session_is_returned(self):
    result = _make_result(True, "2026-06-15T18:00:00+00:00", "2026-06-15T20:00:00+00:00")
    sessions = _normalise_football(result)
    assert len(sessions) == 1
    assert sessions[0].source == "football"
    assert sessions[0].code == "football_202606151800"
    assert sessions[0].duration_in_minutes == 120


# ── _merge_sessions ────────────────────────────────────────────────────────────

class TestMergeSessions:
  def test_empty_list_returns_empty(self):
    assert _merge_sessions([]) == []

  def test_single_session_returned_unchanged(self):
    sessions = [_session("2024-01-07T10:00:00+00:00", "2024-01-07T12:00:00+00:00")]
    assert _merge_sessions(sessions) == sessions

  def test_sessions_sorted_by_start(self):
    s1 = _session("2024-01-14T10:00:00+00:00", "2024-01-14T12:00:00+00:00", "b")
    s2 = _session("2024-01-07T10:00:00+00:00", "2024-01-07T12:00:00+00:00", "a")
    result = _merge_sessions([s1, s2])
    assert result[0].code == "a"
    assert result[1].code == "b"

  def test_exact_duplicate_sessions_deduplicated(self):
    s1 = _session("2024-01-07T10:00:00+00:00", "2024-01-07T12:00:00+00:00", "s1")
    s2 = _session("2024-01-07T10:00:00+00:00", "2024-01-07T12:00:00+00:00", "s2")
    result = _merge_sessions([s1, s2])
    assert len(result) == 1

  def test_overlapping_but_not_identical_sessions_both_retained(self):
    s1 = _session("2024-01-07T10:00:00+00:00", "2024-01-07T12:00:00+00:00", "s1")
    s2 = _session("2024-01-07T10:00:00+00:00", "2024-01-07T13:00:00+00:00", "s2")
    result = _merge_sessions([s1, s2])
    assert len(result) == 2


# ── _sessions_equal ────────────────────────────────────────────────────────────

class TestSessionsEqual:
  def test_two_empty_lists_are_equal(self):
    assert _sessions_equal([], []) is True

  def test_different_lengths_not_equal(self):
    s = _session("2024-01-07T10:00:00+00:00", "2024-01-07T12:00:00+00:00")
    assert _sessions_equal([s], []) is False

  def test_same_sessions_are_equal(self):
    s1 = _session("2024-01-07T10:00:00+00:00", "2024-01-07T12:00:00+00:00", "a")
    s2 = _session("2024-01-07T10:00:00+00:00", "2024-01-07T12:00:00+00:00", "a")
    assert _sessions_equal([s1], [s2]) is True

  def test_different_codes_not_equal(self):
    s1 = _session("2024-01-07T10:00:00+00:00", "2024-01-07T12:00:00+00:00", "a")
    s2 = _session("2024-01-07T10:00:00+00:00", "2024-01-07T12:00:00+00:00", "b")
    assert _sessions_equal([s1], [s2]) is False

  def test_different_start_times_not_equal(self):
    s1 = _session("2024-01-07T10:00:00+00:00", "2024-01-07T12:00:00+00:00", "a")
    s2 = _session("2024-01-07T11:00:00+00:00", "2024-01-07T12:00:00+00:00", "a")
    assert _sessions_equal([s1], [s2]) is False
