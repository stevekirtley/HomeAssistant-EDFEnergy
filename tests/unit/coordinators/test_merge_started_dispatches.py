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

def test_when_charge_overruns_ready_by_then_running_dispatch_carries_on():
  """#51 - the plan stops at the ready by time, the charge does not, and the off peak sensors
  went off underneath a car that was still charging."""
  result = merge_started_dispatches(at("07:10"), "SMART_CONTROL_IN_PROGRESS",
                                    [started("01:00", "07:00")], [planned("01:00", "07:00")])

  assert as_tuples(result) == [(at("01:00"), at("07:30"))]

def test_when_charge_overruns_with_no_plan_left_then_running_dispatch_carries_on():
  result = merge_started_dispatches(at("07:40"), "SMART_CONTROL_IN_PROGRESS",
                                    [started("01:00", "07:30")], [])

  assert as_tuples(result) == [(at("01:00"), at("08:00"))]

def test_when_dispatch_reaches_the_length_limit_then_it_stops_growing():
  """A device left saying it is charging must not extend a dispatch indefinitely."""
  result = merge_started_dispatches(at("20:40"), "SMART_CONTROL_IN_PROGRESS",
                                    [started("06:30", "20:30")], [])

  assert as_tuples(result) == [(at("06:30"), at("20:30"))]

def test_when_dispatch_is_long_but_under_the_limit_then_it_carries_on():
  result = merge_started_dispatches(at("12:10"), "SMART_CONTROL_IN_PROGRESS",
                                    [started("01:00", "12:00")], [])

  assert as_tuples(result) == [(at("01:00"), at("12:30"))]

def test_when_nothing_was_running_then_no_dispatch_invented():
  """Without a plan to go on, the only thing worth trusting is a charge already seen."""
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
