"""Economy 7 night hours on a non-smart meter are midnight to 7am UK time. The window used to
take its UTC offset from today rather than from the rate, so rebuilding a BST day while it was
GMT moved the night rate an hour later (and the other way round)."""
from datetime import datetime, timedelta, timezone
from unittest import mock

import pytest

from homeassistant.util.dt import (
  DEFAULT_TIME_ZONE,
  as_local,
  get_time_zone,
  set_default_time_zone,
)

from custom_components.edfenergy_uk.api_client import EDFEnergyApiClient

@pytest.fixture(autouse=True)
def british_time():
  original = DEFAULT_TIME_ZONE
  set_default_time_zone(get_time_zone("Europe/London"))
  yield
  set_default_time_zone(original)

def night_slots(client: EDFEnergyApiClient, local_day: datetime):
  is_night_rate = client._EDFEnergyApiClient__is_night_rate
  slots = []
  start = local_day
  while start < local_day + timedelta(days=1):
    rate = { "start": start, "end": start + timedelta(minutes=30) }
    if is_night_rate(rate, False):
      slots.append(as_local(start).strftime("%H:%M"))
    start += timedelta(minutes=30)
  return slots

EXPECTED_NIGHT = [f"{hour:02d}:{minute:02d}" for hour in range(7) for minute in (0, 30)]

@pytest.mark.parametrize("day,today", [
  # A BST day, looked at while it's GMT
  (datetime(2026, 10, 20, tzinfo=timezone.utc) - timedelta(hours=1), datetime(2026, 11, 17, 12, tzinfo=timezone.utc)),
  # A GMT day, looked at while it's BST
  (datetime(2026, 3, 20, tzinfo=timezone.utc), datetime(2026, 4, 20, 12, tzinfo=timezone.utc)),
  # Same side of the change
  (datetime(2026, 11, 10, tzinfo=timezone.utc), datetime(2026, 11, 17, 12, tzinfo=timezone.utc)),
])
def test_night_window_is_midnight_to_seven_on_the_rates_own_day(day, today):
  client = EDFEnergyApiClient(api_key="test-key")

  with mock.patch("custom_components.edfenergy_uk.api_client.now", return_value=as_local(today)):
    assert night_slots(client, day) == EXPECTED_NIGHT
