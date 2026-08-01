from datetime import datetime, timezone, timedelta
import pytest

from custom_components.edf_energy.api_client.free_electricity_sessions import FreeElectricitySession
from custom_components.edf_energy.coordinators.free_electricity_sessions import (
  _normalise_sunday_saver,
  _normalise_football,
  _merge_sessions,
  _todays_sessions,
  _sessions_equal,
)
from custom_components.edf_energy.storage.free_electricity_sessions_history import (
  merge_free_electricity_sessions,
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


# ── merge_free_electricity_sessions (persisted history) ─────────────────────────

class TestMergeFreeElectricitySessionsHistory:
  _now = datetime.fromisoformat("2026-06-15T15:00:00+00:00")

  def test_new_session_added_to_empty_history(self):
    s = _session("2026-06-15T19:00:00+00:00", "2026-06-15T21:00:00+00:00", "football_pm")
    result = merge_free_electricity_sessions([], [s], self._now)
    assert [x.code for x in result] == ["football_pm"]

  def test_existing_session_retained_when_provider_stops_reporting(self):
    # history has this morning's finished session; providers now report nothing new
    finished = _session("2026-06-15T10:00:00+00:00", "2026-06-15T12:00:00+00:00", "football_am")
    result = merge_free_electricity_sessions([finished], [], self._now)
    assert [x.code for x in result] == ["football_am"]

  def test_sessions_sorted_by_start(self):
    pm = _session("2026-06-15T19:00:00+00:00", "2026-06-15T21:00:00+00:00", "pm")
    am = _session("2026-06-15T10:00:00+00:00", "2026-06-15T12:00:00+00:00", "am")
    result = merge_free_electricity_sessions([pm], [am], self._now)
    assert [x.code for x in result] == ["am", "pm"]

  def test_same_code_deduplicated_with_new_winning(self):
    # a knockout window whose end shifts once extra time is confirmed keeps one record, updated
    original = _session("2026-06-15T19:00:00+00:00", "2026-06-15T21:00:00+00:00", "football_ko")
    extended = _session("2026-06-15T19:00:00+00:00", "2026-06-15T22:00:00+00:00", "football_ko")
    result = merge_free_electricity_sessions([original], [extended], self._now)
    assert len(result) == 1
    assert result[0].end == extended.end

  def test_sessions_older_than_retention_are_purged(self):
    stale = _session("2026-04-01T19:00:00+00:00", "2026-04-01T21:00:00+00:00", "old")
    recent = _session("2026-06-15T19:00:00+00:00", "2026-06-15T21:00:00+00:00", "new")
    result = merge_free_electricity_sessions([stale, recent], [], self._now)
    assert [x.code for x in result] == ["new"]


# ── _todays_sessions ────────────────────────────────────────────────────────────

class TestTodaysSessions:
  _now = datetime.fromisoformat("2026-06-15T15:00:00+00:00")

  def test_todays_completed_and_upcoming_sessions_are_returned(self):
    am = _session("2026-06-15T10:00:00+00:00", "2026-06-15T12:00:00+00:00", "am")
    pm = _session("2026-06-15T19:00:00+00:00", "2026-06-15T21:00:00+00:00", "pm")
    result = _todays_sessions([am, pm], self._now)
    assert [s.code for s in result] == ["am", "pm"]

  def test_yesterdays_session_is_excluded(self):
    stale = _session("2026-06-14T19:00:00+00:00", "2026-06-14T21:00:00+00:00", "yesterday")
    today = _session("2026-06-15T19:00:00+00:00", "2026-06-15T21:00:00+00:00", "today")
    result = _todays_sessions([stale, today], self._now)
    assert [s.code for s in result] == ["today"]

  def test_repro_issue_24_window_retained_shortly_after_end(self):
    # group-stage match 19:00-21:00; ~6 minutes after it ended it must still be in the feed
    match = _session("2026-06-15T19:00:00+00:00", "2026-06-15T21:00:00+00:00", "football_202606151900")
    just_after = datetime.fromisoformat("2026-06-15T21:06:00+00:00")
    result = _todays_sessions([match], just_after)
    assert [s.code for s in result] == ["football_202606151900"]


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
