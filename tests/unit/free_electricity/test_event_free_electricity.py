from datetime import datetime, timezone, timedelta

from custom_components.edf_energy.coordinators.event_free_electricity import (
  _parse_kickoff_utc,
  _eligible_windows,
  _select_candidate,
  _extra_time_check_required,
  _resolve_window,
)

KO = datetime(2026, 6, 17, 20, 0, tzinfo=timezone.utc)  # England v Croatia, 20:00 UTC
NAME = "England v Croatia"
WINDOWS = [(KO, NAME)]


def _at(minutes_after_ko):
  return KO + timedelta(minutes=minutes_after_ko)


# ── _parse_kickoff_utc ──────────────────────────────────────────────────────────

class TestParseKickoffUtc:
  def test_converts_local_kickoff_to_utc(self):
    assert _parse_kickoff_utc("2026-06-14", "13:00 UTC-6") == datetime(2026, 6, 14, 19, 0, tzinfo=timezone.utc)

  def test_positive_offset(self):
    assert _parse_kickoff_utc("2026-06-17", "23:00 UTC+1") == datetime(2026, 6, 17, 22, 0, tzinfo=timezone.utc)

  def test_unparseable_time_returns_none(self):
    assert _parse_kickoff_utc("2026-06-17", "kick off soon") is None


# ── _eligible_windows ───────────────────────────────────────────────────────────

class TestEligibleWindows:
  def test_keeps_only_england_scotland_and_sorts_by_kickoff(self):
    matches = [
      {"team1": "Spain", "team2": "France", "date": "2026-06-20", "time": "20:00 UTC+0"},
      {"team1": "Scotland", "team2": "Morocco", "date": "2026-06-19", "time": "22:00 UTC+0"},
      {"team1": "England", "team2": "Croatia", "date": "2026-06-17", "time": "20:00 UTC+0"},
    ]
    windows = _eligible_windows(matches)
    assert [n for _, n in windows] == ["England v Croatia", "Scotland v Morocco"]

  def test_ignores_unparseable_kickoffs(self):
    matches = [{"team1": "England", "team2": "Wales", "date": "2026-06-17", "time": "tbc"}]
    assert _eligible_windows(matches) == []


# ── _select_candidate ───────────────────────────────────────────────────────────

class TestSelectCandidate:
  def test_picks_earliest_window_still_within_3h(self):
    assert _select_candidate(WINDOWS, _at(30)) == (KO, NAME)

  def test_skips_matches_whose_3h_window_has_passed(self):
    later = (KO + timedelta(hours=6), "Scotland v Brazil")
    assert _select_candidate([(KO, NAME), later], _at(200)) == later

  def test_returns_none_when_all_windows_passed(self):
    assert _select_candidate(WINDOWS, _at(200)) == (None, None)


# ── _extra_time_check_required ───────────────────────────────────────────────────

class TestExtraTimeCheckRequired:
  def test_false_before_88_minutes(self):
    assert _extra_time_check_required(KO, _at(80), False) is False

  def test_true_inside_the_check_window(self):
    assert _extra_time_check_required(KO, _at(88), False) is True
    assert _extra_time_check_required(KO, _at(150), False) is True

  def test_false_after_3h(self):
    assert _extra_time_check_required(KO, _at(180), False) is False

  def test_false_when_already_extended(self):
    assert _extra_time_check_required(KO, _at(120), True) is False


# ── _resolve_window ──────────────────────────────────────────────────────────────

class TestResolveWindow:
  def test_no_windows_returns_nothing(self):
    assert _resolve_window([], _at(30), False, None, None) == (None, None, None, False)

  def test_upcoming_match_is_two_hours(self):
    start, end, name, extended = _resolve_window(WINDOWS, _at(-10), False, None, None)
    assert (start, end, name, extended) == (KO, KO + timedelta(hours=2), NAME, False)

  def test_early_in_match_is_two_hours_and_does_not_consult_status(self):
    # status present but we're before the check window -> ignored
    start, end, name, extended = _resolve_window(WINDOWS, _at(45), False, None, {"extra_time": True})
    assert end == KO + timedelta(hours=2)
    assert extended is False

  def test_relay_unavailable_falls_back_to_two_hours(self):
    # In the check window but status is None (relay down / timed out / bad JSON).
    start, end, name, extended = _resolve_window(WINDOWS, _at(95), False, None, None)
    assert (end, extended) == (KO + timedelta(hours=2), False)

  def test_undecided_status_stays_two_hours(self):
    status = {"extra_time": False, "match_finished": False}
    _, end, _, extended = _resolve_window(WINDOWS, _at(95), False, None, status)
    assert (end, extended) == (KO + timedelta(hours=2), False)

  def test_extra_time_extends_to_three_hours(self):
    status = {"extra_time": True, "match_finished": False}
    _, end, _, extended = _resolve_window(WINDOWS, _at(118), False, None, status)
    assert (end, extended) == (KO + timedelta(hours=3), True)

  def test_finished_in_normal_time_advances_to_next_match(self):
    later = (KO + timedelta(days=2), "England v Ghana")
    status = {"extra_time": False, "match_finished": True}
    start, end, name, extended = _resolve_window([(KO, NAME), later], _at(116), False, None, status)
    assert (start, name, extended) == (later[0], later[1], False)
    assert end == later[0] + timedelta(hours=2)

  def test_finished_in_normal_time_with_no_next_match_returns_nothing(self):
    status = {"extra_time": False, "match_finished": True}
    assert _resolve_window(WINDOWS, _at(116), False, None, status) == (None, None, None, False)

  def test_already_extended_holds_three_hours_without_status(self):
    # Latched: once extra time was confirmed, later ticks keep 3h even if relay is down.
    _, end, _, extended = _resolve_window(WINDOWS, _at(150), True, KO, None)
    assert (end, extended) == (KO + timedelta(hours=3), True)
