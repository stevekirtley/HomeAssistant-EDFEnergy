from datetime import datetime, timezone

from custom_components.edf_energy.api_client.free_electricity_sessions import FreeElectricitySession
from custom_components.edf_energy.free_electricity import current_or_next_free_electricity_session_event


def _session(code, start, end, source="power_perks"):
  return FreeElectricitySession(code, datetime.fromisoformat(start), datetime.fromisoformat(end), source)


POWER_PERKS = _session("power_perks_202609190400", "2026-09-19T03:00:00+00:00", "2026-09-19T15:00:00+00:00")
SUNDAY_SAVER = _session("sunday_saver_20260927", "2026-09-27T07:00:00+00:00", "2026-09-27T23:00:00+00:00", "sunday_saver")
YESTERDAY = _session("power_perks_202609170400", "2026-09-17T03:00:00+00:00", "2026-09-17T15:00:00+00:00")


def test_returns_none_when_no_sessions():
  assert current_or_next_free_electricity_session_event(datetime(2026, 9, 18, 12, tzinfo=timezone.utc), []) is None
  assert current_or_next_free_electricity_session_event(datetime(2026, 9, 18, 12, tzinfo=timezone.utc), None) is None


def test_returns_next_session_before_it_starts():
  current = datetime(2026, 9, 18, 23, 0, tzinfo=timezone.utc)

  result = current_or_next_free_electricity_session_event(current, [SUNDAY_SAVER, POWER_PERKS, YESTERDAY])

  assert result.code == "power_perks_202609190400"


def test_returns_the_session_in_progress():
  current = datetime(2026, 9, 19, 8, 0, tzinfo=timezone.utc)

  result = current_or_next_free_electricity_session_event(current, [SUNDAY_SAVER, POWER_PERKS])

  assert result.code == "power_perks_202609190400"


def test_moves_on_once_the_session_has_ended():
  current = datetime(2026, 9, 19, 15, 0, 1, tzinfo=timezone.utc)

  result = current_or_next_free_electricity_session_event(current, [POWER_PERKS, SUNDAY_SAVER])

  assert result.code == "sunday_saver_20260927"


def test_source_does_not_matter():
  current = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)

  result = current_or_next_free_electricity_session_event(current, [POWER_PERKS, SUNDAY_SAVER])

  assert result.source == "sunday_saver"


def test_finished_sessions_are_ignored():
  current = datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc)

  assert current_or_next_free_electricity_session_event(current, [YESTERDAY, POWER_PERKS, SUNDAY_SAVER]) is None
