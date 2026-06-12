import logging
from datetime import datetime, timedelta
from typing import Callable, Any

from homeassistant.util.dt import (now, as_local)
from homeassistant.helpers.update_coordinator import (
  DataUpdateCoordinator
)

from ..const import (
  COORDINATOR_REFRESH_IN_SECONDS,
  DATA_EVENT_FREE_ELECTRICITY,
  DATA_FREE_ELECTRICITY_SESSIONS,
  DATA_FREE_ELECTRICITY_SESSIONS_COORDINATOR,
  DATA_SUNDAY_SAVER,
  DOMAIN,
  EVENT_ALL_FREE_ELECTRICITY_SESSIONS,
  EVENT_NEW_FREE_ELECTRICITY_SESSION,
  REFRESH_RATE_IN_MINUTES_FREE_ELECTRICITY_SESSIONS,
)
from . import BaseCoordinatorResult
from .sunday_saver import SundaySaverCoordinatorResult
from .event_free_electricity import EventFreeElectricityCoordinatorResult
from ..api_client.free_electricity_sessions import FreeElectricitySession

_LOGGER = logging.getLogger(__name__)

# Free electricity sessions reach EDF customers through several independent channels:
#   - "sunday_saver": EDF's own Sunday Saver promotion (fetched from EDF's API)
#   - "football":     free windows tied to England/Scotland World Cup matches, derived from
#                     an external schedule because EDF does not expose them via their API
# Rather than have each source publish its own Predbat-facing entity, we aggregate them all
# into a single Octopus-shaped event sensor. Adding a future source is a one-line change:
# write a normaliser that turns its coordinator result into FreeElectricitySession objects
# and append it to _PROVIDERS below.


def _normalise_sunday_saver(result: SundaySaverCoordinatorResult | None) -> list[FreeElectricitySession]:
  if result is None or not result.has_event or result.start is None or result.end is None:
    return []
  code = f"sunday_saver_{result.start.strftime('%Y%m%d')}"
  return [FreeElectricitySession(code, result.start, result.end, "sunday_saver")]


def _normalise_football(result: EventFreeElectricityCoordinatorResult | None) -> list[FreeElectricitySession]:
  if result is None or not result.has_event or result.start is None or result.end is None:
    return []
  code = f"football_{result.start.strftime('%Y%m%d%H%M')}"
  return [FreeElectricitySession(code, result.start, result.end, "football")]


# (hass.data key template, normaliser) pairs. Each key is formatted with the account_id.
_PROVIDERS: list[tuple[str, Callable[[Any], list[FreeElectricitySession]]]] = [
  (DATA_SUNDAY_SAVER, _normalise_sunday_saver),
  (DATA_EVENT_FREE_ELECTRICITY, _normalise_football),
]


def _merge_sessions(sessions: list[FreeElectricitySession]) -> list[FreeElectricitySession]:
  """Sort sessions by start and drop exact duplicates (same start/end).

  Sessions from different sources can legitimately overlap (e.g. a Sunday Saver window and a
  football window on the same afternoon). We keep both - Predbat treats the union as zero
  rate, so overlaps are harmless - but we collapse identical windows so they aren't counted
  twice in the events list.
  """
  ordered = sorted(sessions, key=lambda s: s.start)
  merged: list[FreeElectricitySession] = []
  for session in ordered:
    if any(existing.start == session.start and existing.end == session.end for existing in merged):
      continue
    merged.append(session)
  return merged


class FreeElectricitySessionsCoordinatorResult(BaseCoordinatorResult):
  events: list[FreeElectricitySession]

  def __init__(self, last_evaluated: datetime, request_attempts: int, events: list[FreeElectricitySession], last_error: Exception | None = None):
    super().__init__(last_evaluated, request_attempts, REFRESH_RATE_IN_MINUTES_FREE_ELECTRICITY_SESSIONS, None, last_error)
    self.events = events


def refresh_free_electricity_sessions(
    current: datetime,
    hass,
    account_id: str,
    existing_result: FreeElectricitySessionsCoordinatorResult | None,
    fire_event: Callable[[str, "dict[str, Any]"], None],
) -> FreeElectricitySessionsCoordinatorResult:
  # This coordinator performs no network I/O of its own - it aggregates the cached results of
  # the upstream Sunday Saver and event free electricity coordinators. Those run on the same
  # tick, so we simply recompute the merged list every time and let change detection below
  # decide whether to fire the "new session" events.
  sessions: list[FreeElectricitySession] = []
  for data_key, normaliser in _PROVIDERS:
    upstream = hass.data[DOMAIN][account_id].get(data_key.format(account_id))
    sessions.extend(normaliser(upstream))

  events = _merge_sessions(sessions)

  for event in events:
    is_new = True
    if existing_result is not None:
      for existing_event in existing_result.events:
        if existing_event.code == event.code:
          is_new = False
          break

    if is_new:
      fire_event(EVENT_NEW_FREE_ELECTRICITY_SESSION, {
        "account_id": account_id,
        "event_code": event.code,
        "event_source": event.source,
        "event_start": as_local(event.start),
        "event_end": as_local(event.end),
        "event_duration_in_minutes": event.duration_in_minutes,
      })

  fire_event(EVENT_ALL_FREE_ELECTRICITY_SESSIONS, {
    "account_id": account_id,
    "events": list(map(lambda ev: {
      "code": ev.code,
      "source": ev.source,
      "start": as_local(ev.start),
      "end": as_local(ev.end),
      "duration_in_minutes": ev.duration_in_minutes,
    }, events)),
  })

  return FreeElectricitySessionsCoordinatorResult(current, 1, events)


async def async_setup_free_electricity_sessions_coordinator(hass, account_id: str):

  async def async_update_free_electricity_sessions():
    current = now()
    existing_result = hass.data[DOMAIN][account_id].get(DATA_FREE_ELECTRICITY_SESSIONS.format(account_id))

    result = refresh_free_electricity_sessions(
      current,
      hass,
      account_id,
      existing_result,
      hass.bus.async_fire,
    )

    hass.data[DOMAIN][account_id][DATA_FREE_ELECTRICITY_SESSIONS.format(account_id)] = result
    return hass.data[DOMAIN][account_id][DATA_FREE_ELECTRICITY_SESSIONS.format(account_id)]

  hass.data[DOMAIN][account_id][DATA_FREE_ELECTRICITY_SESSIONS_COORDINATOR.format(account_id)] = DataUpdateCoordinator(
    hass,
    _LOGGER,
    name=f"free_electricity_sessions_{account_id}",
    update_method=async_update_free_electricity_sessions,
    update_interval=timedelta(seconds=COORDINATOR_REFRESH_IN_SECONDS),
    always_update=True
  )

  # Aggregates already-cached upstream data, so a refresh cannot fail on network I/O; run it
  # immediately so the event/calendar/binary entities have data as soon as they are added.
  await hass.data[DOMAIN][account_id][DATA_FREE_ELECTRICITY_SESSIONS_COORDINATOR.format(account_id)].async_refresh()
