import logging
from datetime import datetime, timedelta
from typing import Callable, Any

from homeassistant.util.dt import now, as_local
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from ..const import (
  CONFIG_MAIN_FOOTBALL_FREE_ELECTRICITY,
  COORDINATOR_REFRESH_IN_SECONDS,
  DATA_CLIENT,
  DATA_EVENT_FREE_ELECTRICITY,
  DATA_FOOTBALL_ENROLLMENT,
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
from ..api_client import EDFEnergyApiClient

_LOGGER = logging.getLogger(__name__)

# Free electricity sessions reach EDF customers through several independent channels:
#   - "sunday_saver": EDF's own Sunday Saver promotion (fetched from EDF's API).
#     Always included — EDF's API only returns data for enrolled accounts.
#   - "football": free windows tied to England/Scotland World Cup matches, derived from
#     an external schedule. Requires user opt-in because EDF does not confirm these
#     via their API — we infer them from the public match schedule.
# Adding a future source is a one-line change: write a normaliser and append to _ALWAYS_ON_PROVIDERS
# (for EDF-confirmed sources) or wire it with a separate opt-in flag.


def _normalise_sunday_saver(result: SundaySaverCoordinatorResult | None) -> list[FreeElectricitySession]:
  if result is None or not result.has_event or result.start is None or result.end is None:
    return []
  code = f"sunday_saver_{result.start.strftime('%Y%m%d')}"
  return [FreeElectricitySession(code, result.start, result.end, "sunday_saver")]


def _normalise_football(result: EventFreeElectricityCoordinatorResult | None) -> list[FreeElectricitySession]:
  if result is None or not result.has_event or result.start is None or result.end is None:
    return []
  code = f"football_{result.start.strftime('%Y%m%d%H%M')}"
  sessions = [FreeElectricitySession(code, result.start, result.end, "football")]
  if result.et_start is not None and result.et_end is not None:
    et_code = f"football_et_{result.et_start.strftime('%Y%m%d%H%M')}"
    sessions.append(FreeElectricitySession(et_code, result.et_start, result.et_end, "football_et"))
  return sessions


_ALWAYS_ON_PROVIDERS: list[tuple[str, Callable[[Any], list[FreeElectricitySession]]]] = [
  (DATA_SUNDAY_SAVER, _normalise_sunday_saver),
]

# ARCHIVED — World Cup 2026 ended 2026-07-19. Football provider is dormant.
# _normalise_football is kept so historic football_* session codes remain parseable.
# Re-enable by restoring the entry below when a new football tournament begins.
_OPT_IN_PROVIDERS: list[tuple[str, Callable[[Any], list[FreeElectricitySession]], str]] = [
  # (data_key_template, normaliser, config_key)
  # (DATA_EVENT_FREE_ELECTRICITY, _normalise_football, CONFIG_MAIN_FOOTBALL_FREE_ELECTRICITY),
]


def _merge_sessions(sessions: list[FreeElectricitySession]) -> list[FreeElectricitySession]:
  """Sort sessions by start and drop exact duplicates (same start AND end).

  Overlapping sessions from different sources are both retained — Predbat treats the union
  as zero rate, so overlaps are harmless, but identical windows must not be double-counted.
  """
  ordered = sorted(sessions, key=lambda s: s.start)
  merged: list[FreeElectricitySession] = []
  for session in ordered:
    if not any(e.start == session.start and e.end == session.end for e in merged):
      merged.append(session)
  return merged


def _sessions_equal(a: list[FreeElectricitySession], b: list[FreeElectricitySession]) -> bool:
  if len(a) != len(b):
    return False
  return all(x.code == y.code and x.start == y.start and x.end == y.end for x, y in zip(a, b))


_ENROLLMENT_CACHE_SECONDS = 3600  # Re-check enrollment once per hour


async def _async_get_football_enrollment(hass, account_id: str) -> bool | None:
  # ARCHIVED — World Cup 2026 ended 2026-07-19. Always returns None (no enrollment check).
  # Restore body below when a new football tournament begins.
  return None

  # ↓↓↓ archived enrollment-check body ↓↓↓
  """Return cached enrollment status, re-fetching from the EDF API when stale.

  Returns True (enrolled), False (not enrolled), or None if the API is unavailable.
  """
  cache_key = DATA_FOOTBALL_ENROLLMENT.format(account_id)
  cached = hass.data[DOMAIN][account_id].get(cache_key)
  if cached is not None:
    status, checked_at = cached
    if (now() - checked_at).total_seconds() < _ENROLLMENT_CACHE_SECONDS:
      return status

  client: EDFEnergyApiClient = hass.data[DOMAIN][account_id].get(DATA_CLIENT)
  if client is None:
    return None

  status = await client.async_get_football_enrollment_status(account_id)
  # Only cache a definitive result — None means the API was unavailable, so retry next tick
  if status is not None:
    hass.data[DOMAIN][account_id][cache_key] = (status, now())
  return status


class FreeElectricitySessionsCoordinatorResult(BaseCoordinatorResult):
  events: list[FreeElectricitySession]
  football_enabled: bool
  football_enrollment_auto_detected: bool

  def __init__(
    self,
    last_evaluated: datetime,
    request_attempts: int,
    events: list[FreeElectricitySession],
    football_enabled: bool = False,
    football_enrollment_auto_detected: bool = False,
    last_error: Exception | None = None,
  ):
    super().__init__(last_evaluated, request_attempts, REFRESH_RATE_IN_MINUTES_FREE_ELECTRICITY_SESSIONS, None, last_error)
    self.events = events
    self.football_enabled = football_enabled
    self.football_enrollment_auto_detected = football_enrollment_auto_detected


def refresh_free_electricity_sessions(
  current: datetime,
  hass,
  account_id: str,
  existing_result: FreeElectricitySessionsCoordinatorResult | None,
  fire_event: Callable[[str, dict[str, Any]], None],
  football_enabled: bool = False,
  football_enrollment_auto_detected: bool = False,
) -> FreeElectricitySessionsCoordinatorResult:
  sessions: list[FreeElectricitySession] = []

  for data_key, normaliser in _ALWAYS_ON_PROVIDERS:
    upstream = hass.data[DOMAIN][account_id].get(data_key.format(account_id))
    sessions.extend(normaliser(upstream))

  for data_key, normaliser, config_key in _OPT_IN_PROVIDERS:
    if config_key == CONFIG_MAIN_FOOTBALL_FREE_ELECTRICITY and not football_enabled:
      continue
    upstream = hass.data[DOMAIN][account_id].get(data_key.format(account_id))
    sessions.extend(normaliser(upstream))

  events = _merge_sessions(sessions)

  # Fire "new session" events for any session not seen in the previous result
  for event in events:
    is_new = existing_result is None or not any(e.code == event.code for e in existing_result.events)
    if is_new:
      fire_event(EVENT_NEW_FREE_ELECTRICITY_SESSION, {
        "account_id": account_id,
        "event_code": event.code,
        "event_source": event.source,
        "event_start": as_local(event.start),
        "event_end": as_local(event.end),
        "event_duration_in_minutes": event.duration_in_minutes,
      })

  # Fire the "all sessions" bus event on every coordinator tick so that automations
  # using the event entity as a trigger get a regular heartbeat — matching the behaviour
  # of the upstream OctopusEnergy integration.
  fire_event(EVENT_ALL_FREE_ELECTRICITY_SESSIONS, {
      "account_id": account_id,
      "football_free_electricity_enabled": football_enabled,
      "football_enrollment_auto_detected": football_enrollment_auto_detected,
      "events": [
        {
          "code": ev.code,
          "source": ev.source,
          "start": as_local(ev.start),
          "end": as_local(ev.end),
          "duration_in_minutes": ev.duration_in_minutes,
        }
        for ev in events
      ],
    })

  return FreeElectricitySessionsCoordinatorResult(current, 1, events, football_enabled, football_enrollment_auto_detected)


async def async_setup_free_electricity_sessions_coordinator(hass, account_id: str, entry):
  async def async_update_free_electricity_sessions():
    current = now()
    existing_result = hass.data[DOMAIN][account_id].get(DATA_FREE_ELECTRICITY_SESSIONS.format(account_id))

    # Try to auto-detect enrollment from the EDF website API; fall back to manual toggle if unavailable.
    enrollment = await _async_get_football_enrollment(hass, account_id)
    if enrollment is not None:
      football_enabled = enrollment
      football_enrollment_auto_detected = True
    else:
      football_enabled = entry.options.get(CONFIG_MAIN_FOOTBALL_FREE_ELECTRICITY, False)
      football_enrollment_auto_detected = False

    result = refresh_free_electricity_sessions(
      current, hass, account_id, existing_result, hass.bus.async_fire,
      football_enabled, football_enrollment_auto_detected,
    )
    hass.data[DOMAIN][account_id][DATA_FREE_ELECTRICITY_SESSIONS.format(account_id)] = result
    return result

  hass.data[DOMAIN][account_id][DATA_FREE_ELECTRICITY_SESSIONS_COORDINATOR.format(account_id)] = DataUpdateCoordinator(
    hass,
    _LOGGER,
    name=f"free_electricity_sessions_{account_id}",
    update_method=async_update_free_electricity_sessions,
    update_interval=timedelta(seconds=COORDINATOR_REFRESH_IN_SECONDS),
    always_update=True,
  )

  await hass.data[DOMAIN][account_id][DATA_FREE_ELECTRICITY_SESSIONS_COORDINATOR.format(account_id)].async_refresh()
