from datetime import datetime, timezone, timedelta

from custom_components.edf_energy.coordinators.event_free_electricity import (
  _eligible_windows,
  _select_candidate,
  _extra_time_check_required,
  _resolve_window,
)

KO = datetime(2026, 6, 17, 20, 0, tzinfo=timezone.utc)  # England v Croatia, 20:00 UTC
NAME = "England v Croatia"

# Group stage match — no extra time possible
GROUP_WINDOWS = [(KO, NAME, False)]
# Knockout match — extra time possible
KO_WINDOWS = [(KO, NAME, True)]


def _at(minutes_after_ko):
  return KO + timedelta(minutes=minutes_after_ko)


# ── _eligible_windows ───────────────────────────────────────────────────────────

KO_TS = int(KO.timestamp())

class TestEligibleWindows:
  def test_converts_timestamp_and_builds_name(self):
    matches = [{"timestamp": KO_TS, "home": "England", "away": "Croatia", "round": "group-stage"}]
    windows = _eligible_windows(matches)
    assert windows == [(KO, "England v Croatia", False)]

  def test_sorts_by_kickoff(self):
    later = KO + timedelta(hours=48)
    matches = [
      {"timestamp": int(later.timestamp()), "home": "Scotland", "away": "Morocco", "round": "group-stage"},
      {"timestamp": KO_TS, "home": "England", "away": "Croatia", "round": "group-stage"},
    ]
    windows = _eligible_windows(matches)
    assert [n for _, n, _ in windows] == ["England v Croatia", "Scotland v Morocco"]

  def test_skips_fixture_with_no_timestamp(self):
    matches = [{"home": "England", "away": "Wales", "round": "group-stage"}]
    assert _eligible_windows(matches) == []

  def test_skips_fixture_with_invalid_timestamp(self):
    matches = [{"timestamp": "tbc", "home": "England", "away": "Wales", "round": "group-stage"}]
    assert _eligible_windows(matches) == []

  def test_group_stage_match_is_not_knockout(self):
    matches = [{"timestamp": KO_TS, "home": "England", "away": "Croatia", "round": "group-stage"}]
    windows = _eligible_windows(matches)
    assert windows[0][2] is False

  def test_knockout_match_is_knockout(self):
    matches = [{"timestamp": KO_TS, "home": "England", "away": "France", "round": "quarter-final"}]
    windows = _eligible_windows(matches)
    assert windows[0][2] is True


# ── _select_candidate ───────────────────────────────────────────────────────────

class TestSelectCandidate:
  def test_picks_earliest_window_still_within_max(self):
    assert _select_candidate(KO_WINDOWS, _at(30)) == (KO, NAME, True)

  def test_group_stage_match_expires_after_2h(self):
    assert _select_candidate(GROUP_WINDOWS, _at(121)) == (None, None, False)

  def test_knockout_match_stays_active_until_3h(self):
    assert _select_candidate(KO_WINDOWS, _at(150)) == (KO, NAME, True)
    assert _select_candidate(KO_WINDOWS, _at(181)) == (None, None, False)

  def test_skips_matches_whose_max_window_has_passed(self):
    later = (KO + timedelta(hours=6), "Scotland v Brazil", False)
    assert _select_candidate([(KO, NAME, True), later], _at(200)) == later

  def test_returns_none_when_all_windows_passed(self):
    assert _select_candidate(KO_WINDOWS, _at(200)) == (None, None, False)


# ── _extra_time_check_required ───────────────────────────────────────────────────

class TestExtraTimeCheckRequired:
  def test_false_before_88_minutes(self):
    assert _extra_time_check_required(KO, _at(80), False, True) is False

  def test_true_inside_the_check_window(self):
    assert _extra_time_check_required(KO, _at(88), False, True) is True
    assert _extra_time_check_required(KO, _at(150), False, True) is True

  def test_false_after_3h(self):
    assert _extra_time_check_required(KO, _at(180), False, True) is False

  def test_false_when_already_extended(self):
    assert _extra_time_check_required(KO, _at(120), True, True) is False

  def test_false_for_group_stage_match_regardless_of_time(self):
    assert _extra_time_check_required(KO, _at(88), False, False) is False
    assert _extra_time_check_required(KO, _at(150), False, False) is False


# ── _resolve_window ──────────────────────────────────────────────────────────────
# Signature: (windows, current, already_et_start: datetime|None, status) -> (start, end, name, et_start, et_end)
# already_et_start is None when ET has not been confirmed; equals start+2h once it has been.
# ET is surfaced as a separate slot (et_start, et_end) rather than extending the main window.

ET_START = KO + timedelta(hours=2)  # the value passed as already_et_start once ET is latched

class TestResolveWindow:
  def test_no_windows_returns_nothing(self):
    assert _resolve_window([], _at(30), None, None) == (None, None, None, None, None)

  def test_upcoming_match_is_two_hours(self):
    start, end, name, et_start, et_end = _resolve_window(KO_WINDOWS, _at(-10), None, None)
    assert (start, end, name, et_start) == (KO, KO + timedelta(hours=2), NAME, None)

  def test_early_in_match_is_two_hours_and_does_not_consult_status(self):
    # status present but we're before the check window -> ignored
    start, end, name, et_start, et_end = _resolve_window(KO_WINDOWS, _at(45), None, {"extra_time": True})
    assert end == KO + timedelta(hours=2)
    assert et_start is None

  def test_relay_unavailable_falls_back_to_two_hours(self):
    # In the check window but status is None (relay down / timed out / bad JSON).
    start, end, name, et_start, et_end = _resolve_window(KO_WINDOWS, _at(95), None, None)
    assert (end, et_start) == (KO + timedelta(hours=2), None)

  def test_undecided_status_stays_two_hours(self):
    status = {"extra_time": False, "match_finished": False}
    _, end, _, et_start, _ = _resolve_window(KO_WINDOWS, _at(95), None, status)
    assert (end, et_start) == (KO + timedelta(hours=2), None)

  def test_extra_time_returns_separate_et_slot_for_knockout(self):
    status = {"extra_time": True, "match_finished": False}
    start, end, name, et_start, et_end = _resolve_window(KO_WINDOWS, _at(118), None, status)
    assert end == KO + timedelta(hours=2)
    assert (et_start, et_end) == (KO + timedelta(hours=2), KO + timedelta(hours=3))

  def test_group_stage_match_never_gets_et_slot(self):
    # Even with extra_time signal, group stage never gets an ET slot
    status = {"extra_time": True, "match_finished": False}
    _, end, _, et_start, et_end = _resolve_window(GROUP_WINDOWS, _at(95), None, status)
    assert (end, et_start) == (KO + timedelta(hours=2), None)

  def test_finished_in_normal_time_advances_to_next_match(self):
    later = (KO + timedelta(days=2), "England v Ghana", False)
    status = {"extra_time": False, "match_finished": True}
    start, end, name, et_start, _ = _resolve_window([(KO, NAME, True), later], _at(116), None, status)
    assert (start, name, et_start) == (later[0], later[1], None)
    assert end == later[0] + timedelta(hours=2)

  def test_finished_in_normal_time_with_no_next_match_returns_nothing(self):
    status = {"extra_time": False, "match_finished": True}
    assert _resolve_window(KO_WINDOWS, _at(116), None, status) == (None, None, None, None, None)

  def test_already_extended_holds_et_slot_without_status(self):
    # Latched: once ET was confirmed, later ticks keep the ET slot even if relay is down.
    _, end, _, et_start, et_end = _resolve_window(KO_WINDOWS, _at(150), ET_START, None)
    assert end == KO + timedelta(hours=2)
    assert (et_start, et_end) == (KO + timedelta(hours=2), KO + timedelta(hours=3))
