from datetime import datetime, timedelta
import pytest

from homeassistant.util.dt import (
  DEFAULT_TIME_ZONE,
  as_utc,
  get_time_zone,
  set_default_time_zone,
  start_of_local_day,
)

from custom_components.edfenergy_uk.coordinators.previous_consumption_and_rates import (
  get_expected_slots_in_day,
  get_latest_day,
)

@pytest.fixture(autouse=True)
def british_time():
  """Days are only ever twenty three or twenty five hours long somewhere that keeps summer
  time, and the test box runs in UTC, so the clock change is invisible without this."""
  original = DEFAULT_TIME_ZONE
  set_default_time_zone(get_time_zone("Europe/London"))
  yield
  set_default_time_zone(original)

def build_day(day: str, slots: int | None = None):
  """Half hourly consumption for a local day, as the API hands it over."""
  start = start_of_local_day(datetime.fromisoformat(day))
  if slots is None:
    slots = get_expected_slots_in_day(start)

  data = []
  for index in range(slots):
    slot_start = as_utc(start) + timedelta(minutes=30 * index)
    data.append({
      "start": slot_start,
      "end": slot_start + timedelta(minutes=30),
      "consumption": 1,
    })

  return data

@pytest.mark.parametrize("day,expected",[
  ("2026-10-24", 48),
  # The clocks go back, so the day is twenty five hours long
  ("2026-10-25", 50),
  # And forward, so this one is twenty three
  ("2026-03-29", 46),
])
def test_when_day_length_varies_then_expected_slots_matches(day: str, expected: int):
  assert get_expected_slots_in_day(start_of_local_day(datetime.fromisoformat(day))) == expected

@pytest.mark.parametrize("day",[
  "2026-10-24",
  # A whole day is a whole day whatever the clocks did - this one is the fifty slot day that
  # used to be thrown away and never asked for again
  "2026-10-25",
  "2026-03-29",
])
def test_when_day_is_complete_then_day_returned(day: str):
  consumption = build_day(day)

  result = get_latest_day(consumption)

  assert result is not None
  assert len(result) == len(consumption)
  assert result[0]["start"] == consumption[0]["start"]
  assert result[-1]["end"] == consumption[-1]["end"]

@pytest.mark.parametrize("day,slots",[
  ("2026-10-24", 47),
  # Forty eight is a whole day on almost every day of the year, and two slots short on this one
  ("2026-10-25", 48),
  ("2026-03-29", 45),
])
def test_when_day_is_short_then_none_returned(day: str, slots: int):
  assert get_latest_day(build_day(day, slots)) is None

def test_when_several_days_present_then_latest_complete_day_returned():
  consumption = build_day("2026-10-25") + build_day("2026-10-26")

  result = get_latest_day(consumption)

  assert result is not None
  assert len(result) == 48
  assert result[0]["start"] == as_utc(start_of_local_day(datetime.fromisoformat("2026-10-26")))

def test_when_latest_day_is_partial_then_previous_complete_day_returned():
  consumption = build_day("2026-10-25") + build_day("2026-10-26", 12)

  result = get_latest_day(consumption)

  assert result is not None
  assert len(result) == 50

def test_when_no_data_then_none_returned():
  assert get_latest_day([]) is None
  assert get_latest_day(None) is None
