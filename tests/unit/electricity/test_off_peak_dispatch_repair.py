"""When the off peak sensor runs the one-off repair of its stored history, and when it doesn't.

The repair itself is tested on its own. These cover the decisions around it: an export meter
has nothing to repair, a sensor that cannot see a charger yet must look again next time rather
than record that it is done, and once it is done that has to survive the ordinary saves that
follow, which happen on every refresh.
"""
from datetime import datetime, timedelta, timezone

import pytest

from custom_components.edfenergy_uk.api_client.intelligent_dispatches import (
  IntelligentDispatches,
  SimpleIntelligentDispatchItem,
)
from custom_components.edfenergy_uk.electricity import off_peak as off_peak_module
from custom_components.edfenergy_uk.electricity.off_peak import EDFEnergyElectricityOffPeak
from custom_components.edfenergy_uk.storage.off_peak_history import OffPeakWindowRecord

DAY = datetime(2026, 10, 20, tzinfo=timezone.utc)

def sensor(is_export=False, device_ids=("device-1",)):
  """The sensor without a coordinator or Home Assistant behind it - only the repair is used."""
  entity = EDFEnergyElectricityOffPeak.__new__(EDFEnergyElectricityOffPeak)
  entity._hass = object()
  entity._mpan = "1111111111111"
  entity._serial_number = "SERIAL"
  entity._is_export = is_export
  entity._account_id = "A-XXXXXX"
  entity._intelligent_device_ids = list(device_ids)
  entity._dispatch_repair_done = False
  entity._off_peak_history = [
    OffPeakWindowRecord(DAY, DAY + timedelta(hours=5), False),
    OffPeakWindowRecord(DAY + timedelta(hours=5), DAY + timedelta(hours=7), True),
  ]
  return entity

@pytest.fixture
def stores(monkeypatch):
  """Stand-ins for the two stores, recording what was saved."""
  state = {"saved": [], "dispatches": {
    "device-1": IntelligentDispatches(None, [], [], [
      SimpleIntelligentDispatchItem(DAY + timedelta(hours=5), DAY + timedelta(hours=11, minutes=30)),
    ]),
  }}

  async def load_dispatches(hass, account_id, device_id):
    return state["dispatches"].get(device_id)

  async def save(hass, mpan, serial_number, windows, dispatch_repair_done=False):
    state["saved"].append((list(windows), dispatch_repair_done))

  monkeypatch.setattr(off_peak_module, "async_load_cached_intelligent_dispatches", load_dispatches)
  monkeypatch.setattr(off_peak_module, "async_save_cached_off_peak_history", save)
  monkeypatch.setattr(off_peak_module, "start_of_local_day", lambda: DAY + timedelta(days=10))
  return state

@pytest.mark.asyncio
async def test_a_charge_that_ran_is_put_back_and_the_repair_is_recorded(stores):
  # Arrange
  entity = sensor()

  # Act
  await entity._async_repair_from_dispatches()

  # Assert
  assert entity._dispatch_repair_done is True
  assert [(w.start.hour, w.end.hour, w.end.minute) for w in entity._off_peak_history if w.is_intelligent_adjusted] == [
    (5, 7, 0), (7, 11, 30)]
  windows, done = stores["saved"][-1]
  assert done is True and len(windows) == 3

@pytest.mark.asyncio
async def test_an_export_meter_is_left_alone(stores):
  """Export rates never carry smart charging windows, so there is nothing that could be lost."""
  # Arrange
  entity = sensor(is_export=True)

  # Act
  await entity._async_repair_from_dispatches()

  # Assert
  assert entity._dispatch_repair_done is False
  assert stores["saved"] == []

@pytest.mark.asyncio
async def test_without_a_charger_it_looks_again_next_time(stores):
  """The devices may simply not have loaded yet, and recording it as done would be for good."""
  # Arrange
  entity = sensor(device_ids=())

  # Act
  await entity._async_repair_from_dispatches()

  # Assert
  assert entity._dispatch_repair_done is False
  assert stores["saved"] == []

@pytest.mark.asyncio
async def test_when_no_dispatches_could_be_read_it_looks_again_next_time(stores):
  # Arrange
  entity = sensor(device_ids=("device-not-stored",))

  # Act
  await entity._async_repair_from_dispatches()

  # Assert
  assert entity._dispatch_repair_done is False
  assert stores["saved"] == []

@pytest.mark.asyncio
async def test_once_done_it_stays_recorded_through_ordinary_saves(stores):
  """Every refresh saves the history, and that must not wipe the record of the repair."""
  # Arrange
  entity = sensor()
  await entity._async_repair_from_dispatches()

  # Act - the save a coordinator refresh makes
  await entity._async_save_history()

  # Assert
  assert stores["saved"][-1][1] is True
