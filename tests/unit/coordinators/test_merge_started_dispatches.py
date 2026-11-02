from datetime import datetime, timedelta
import pytest

from homeassistant.util.dt import as_utc

from custom_components.edfenergy_uk.api_client.intelligent_dispatches import (
  IntelligentDispatchItem,
  SimpleIntelligentDispatchItem,
)
from custom_components.edfenergy_uk.coordinators.intelligent_dispatches import merge_started_dispatches

def at(time: str) -> datetime:
  return as_utc(datetime.fromisoformat(f"2026-10-20T{time}:00"))

def planned(start: str, end: str, source: str = "smart-charge") -> IntelligentDispatchItem:
  return IntelligentDispatchItem(at(start), at(end), 1.0, source, None)

def started(start: str, end: str) -> SimpleIntelligentDispatchItem:
  return SimpleIntelligentDispatchItem(at(start), at(end))

def as_tuples(dispatches: list[SimpleIntelligentDispatchItem]):
  return [(d.start, d.end) for d in dispatches]

def test_when_plan_covers_now_then_current_half_hour_recorded():
  result = merge_started_dispatches(at("02:15"), "SMART_CONTROL_IN_PROGRESS", [], [planned("01:00", "07:00")])

  assert as_tuples(result) == [(at("02:00"), at("02:30"))]

def test_when_plan_covers_now_then_running_dispatch_extended():
  result = merge_started_dispatches(at("02:40"), "SMART_CONTROL_IN_PROGRESS",
                                    [started("01:00", "02:30")], [planned("01:00", "07:00")])

  assert as_tuples(result) == [(at("01:00"), at("03:00"))]

def test_when_nothing_was_running_then_no_dispatch_invented():
  """No plan covering now means no record, whatever the device says it is doing."""
  result = merge_started_dispatches(at("07:10"), "SMART_CONTROL_IN_PROGRESS", [], [])

  assert as_tuples(result) == []

def test_when_gap_since_last_dispatch_then_no_dispatch_invented():
  result = merge_started_dispatches(at("07:40"), "SMART_CONTROL_IN_PROGRESS",
                                    [started("01:00", "07:00")], [])

  assert as_tuples(result) == [(at("01:00"), at("07:00"))]

@pytest.mark.parametrize("state",["SMART_CONTROL_CAPABLE","BOOSTING","SMART_CONTROL_NOT_AVAILABLE"])
def test_when_not_charging_under_smart_control_then_dispatch_not_extended(state: str):
  result = merge_started_dispatches(at("07:10"), state, [started("01:00", "07:00")], [])

  assert as_tuples(result) == [(at("01:00"), at("07:00"))]

def test_when_plan_is_a_bump_charge_then_dispatch_not_recorded():
  result = merge_started_dispatches(at("02:15"), "SMART_CONTROL_IN_PROGRESS", [],
                                    [planned("01:00", "07:00", "bump-charge")])

  assert as_tuples(result) == []

def test_when_plugged_in_and_idle_between_windows_then_dispatch_not_extended():
  """A charge that has finished, with the next window hours away.

  SMART_CONTROL_IN_PROGRESS stays true the whole time the car sits plugged in under smart
  control, so inferring a dispatch from it ran a finished charge on for hours: the off peak
  sensors stayed on, the discounted rate was applied to half hours nobody charged in, and
  each refresh extended the same window again because it ended on the boundary.
  """
  result = merge_started_dispatches(at("18:45"), "SMART_CONTROL_IN_PROGRESS",
                                    [started("09:30", "13:30")],
                                    [planned("23:00", "23:30")])

  assert as_tuples(result) == [(at("09:30"), at("13:30"))]

def test_when_a_bump_charge_follows_a_dispatch_then_dispatch_not_extended():
  """A bump charge is deliberately not a dispatch, and must not inherit one that just ended."""
  result = merge_started_dispatches(at("07:10"), "SMART_CONTROL_IN_PROGRESS",
                                    [started("01:00", "07:00")],
                                    [planned("07:00", "09:00", "bump-charge")])

  assert as_tuples(result) == [(at("01:00"), at("07:00"))]
