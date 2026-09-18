from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from homeassistant.util.dt import as_local

from custom_components.edf_energy.api_client.free_electricity_sessions import FreeElectricitySession
from custom_components.edf_energy.const import (
  DATA_FREE_ELECTRICITY_SESSIONS,
  DATA_FREE_ELECTRICITY_SESSIONS_HISTORY,
  DOMAIN,
  EVENT_ALL_FREE_ELECTRICITY_SESSIONS,
)
from custom_components.edf_energy.free_electricity.free_electricity_sessions_events import EDFEnergyFreeElectricitySessionEvents

ACCOUNT_ID = "A-12345"


def _session(code, start, end, source):
  return FreeElectricitySession(code, datetime.fromisoformat(start), datetime.fromisoformat(end), source)


# The situation from issue #33: a Sunday Saver session weeks ago in the history, and a Power Perks
# session for tomorrow that arrived after the last state Home Assistant recorded for the entity.
SUNDAY_SAVER = _session("sunday_saver_20260809", "2026-08-09T07:00:00+00:00", "2026-08-09T23:00:00+00:00", "sunday_saver")
POWER_PERKS = _session("power_perks_202609190400", "2026-09-19T03:00:00+00:00", "2026-09-19T15:00:00+00:00", "power_perks")


def _hass(result=None, history=None):
  hass = MagicMock()
  hass.data = {DOMAIN: {ACCOUNT_ID: {}}}
  if result is not None:
    hass.data[DOMAIN][ACCOUNT_ID][DATA_FREE_ELECTRICITY_SESSIONS.format(ACCOUNT_ID)] = result
  if history is not None:
    hass.data[DOMAIN][ACCOUNT_ID][DATA_FREE_ELECTRICITY_SESSIONS_HISTORY.format(ACCOUNT_ID)] = history
  return hass


def _coordinator_result(events, football_enabled=False, football_enrollment_auto_detected=False):
  return SimpleNamespace(
    events=events,
    football_enabled=football_enabled,
    football_enrollment_auto_detected=football_enrollment_auto_detected,
  )


async def _added_entity(hass):
  entity = EDFEnergyFreeElectricitySessionEvents(hass, ACCOUNT_ID)
  await entity.async_added_to_hass()
  entity.async_write_ha_state = MagicMock()
  return entity


@pytest.mark.asyncio
async def test_events_are_seeded_from_the_coordinator_when_added():
  # The coordinator has already run (and fired its first event, unheard) by the time the entity
  # is registered, so the entity must take the current sessions from its result rather than wait
  # for the next bus event.
  hass = _hass(result=_coordinator_result([POWER_PERKS]), history=[SUNDAY_SAVER, POWER_PERKS])

  entity = await _added_entity(hass)

  attributes = entity.extra_state_attributes
  assert [e["code"] for e in attributes["events"]] == ["power_perks_202609190400"]
  assert attributes["events"][0] == {
    "code": "power_perks_202609190400",
    "source": "power_perks",
    "start": as_local(POWER_PERKS.start),
    "end": as_local(POWER_PERKS.end),
    "duration_in_minutes": 12 * 60,
  }
  assert [w["code"] for w in attributes["free_electricity_windows"]] == ["sunday_saver_20260809", "power_perks_202609190400"]


@pytest.mark.asyncio
async def test_football_flags_are_seeded_from_the_coordinator_when_added():
  hass = _hass(result=_coordinator_result([], football_enabled=True, football_enrollment_auto_detected=True))

  entity = await _added_entity(hass)

  attributes = entity.extra_state_attributes
  assert attributes["football_free_electricity_enabled"] is True
  assert attributes["football_enrollment_auto_detected"] is True


@pytest.mark.asyncio
async def test_events_are_empty_when_the_coordinator_has_not_run():
  entity = await _added_entity(_hass())

  attributes = entity.extra_state_attributes
  assert attributes["events"] == []
  assert attributes["free_electricity_windows"] == []


@pytest.mark.asyncio
async def test_events_follow_the_next_bus_event():
  entity = await _added_entity(_hass(result=_coordinator_result([])))
  hass_event = SimpleNamespace(
    event_type=EVENT_ALL_FREE_ELECTRICITY_SESSIONS,
    data={
      "account_id": ACCOUNT_ID,
      "football_free_electricity_enabled": False,
      "football_enrollment_auto_detected": False,
      "events": [{"code": "power_perks_202609190400"}],
      "free_electricity_windows": [{"code": "sunday_saver_20260809"}, {"code": "power_perks_202609190400"}],
    },
  )

  entity._async_handle_event(hass_event)

  attributes = entity.extra_state_attributes
  assert attributes["events"] == [{"code": "power_perks_202609190400"}]
  assert [w["code"] for w in attributes["free_electricity_windows"]] == ["sunday_saver_20260809", "power_perks_202609190400"]
  entity.async_write_ha_state.assert_called_once()


@pytest.mark.asyncio
async def test_bus_events_for_another_account_are_ignored():
  entity = await _added_entity(_hass(result=_coordinator_result([POWER_PERKS])))
  hass_event = SimpleNamespace(
    event_type=EVENT_ALL_FREE_ELECTRICITY_SESSIONS,
    data={"account_id": "A-99999", "events": [], "free_electricity_windows": []},
  )

  entity._async_handle_event(hass_event)

  assert [e["code"] for e in entity.extra_state_attributes["events"]] == ["power_perks_202609190400"]
  entity.async_write_ha_state.assert_not_called()
