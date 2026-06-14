import logging
import re
from datetime import datetime, timezone, timedelta

import aiohttp
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util.dt import utcnow

from ..const import (
  COORDINATOR_REFRESH_IN_SECONDS,
  DATA_EVENT_FREE_ELECTRICITY,
  DATA_EVENT_FREE_ELECTRICITY_COORDINATOR,
  DOMAIN,
  EXTRA_TIME_RELAY_URL,
  REFRESH_RATE_IN_MINUTES_EVENT_FREE_ELECTRICITY,
)
from . import BaseCoordinatorResult

_LOGGER = logging.getLogger(__name__)

_WORLDCUP_URL = "https://raw.githubusercontent.com/openfootball/worldcup.json/refs/heads/master/2026/worldcup.json"
_ELIGIBLE_TEAMS = {"England", "Scotland"}

# Standard free window from kickoff; extended to 3h when a match goes to extra time.
_FREE_WINDOW = timedelta(hours=2)
_EXTRA_FREE_WINDOW = timedelta(hours=3)
# Real elapsed time from kickoff before extra time can be confirmed (covers two halves,
# half-time and stoppage), and how often we poll the relay while it's undecided.
_EXTRA_TIME_CHECK_AFTER = timedelta(minutes=88)
_EXTRA_TIME_POLL = timedelta(minutes=2)


class EventFreeElectricityCoordinatorResult(BaseCoordinatorResult):
  has_event: bool
  start: datetime | None
  end: datetime | None
  event_name: str | None
  extended: bool

  def __init__(
    self,
    last_evaluated: datetime,
    request_attempts: int,
    start: datetime | None,
    end: datetime | None,
    event_name: str | None,
    extended: bool = False,
    last_error=None,
  ):
    super().__init__(last_evaluated, request_attempts, REFRESH_RATE_IN_MINUTES_EVENT_FREE_ELECTRICITY, None, last_error)
    self.start = start
    self.end = end
    self.event_name = event_name
    self.extended = extended
    self.has_event = start is not None and end is not None

    # Tighten the refresh cadence around a match so we (a) wake up in time to start
    # checking for extra time, (b) poll while it's undecided, and (c) advance to the
    # next match once this window ends.
    if self.has_event:
      current = last_evaluated
      check_start = start + _EXTRA_TIME_CHECK_AFTER
      check_end = start + _EXTRA_FREE_WINDOW
      if not extended:
        if current < check_start:
          self.next_refresh = min(self.next_refresh, check_start)
        elif current < check_end:
          self.next_refresh = min(self.next_refresh, current + _EXTRA_TIME_POLL)
      after_end = end + timedelta(minutes=1)
      if current < after_end:
        self.next_refresh = min(self.next_refresh, after_end)


def _parse_kickoff_utc(date_str: str, time_str: str) -> datetime | None:
  """Parse "2026-06-14" + "13:00 UTC-6" into a UTC datetime."""
  m = re.match(r'(\d{2}):(\d{2})\s+UTC([+-]\d+)', time_str)
  if not m:
    return None
  hour = int(m.group(1))
  minute = int(m.group(2))
  offset_hours = int(m.group(3))
  tz = timezone(timedelta(hours=offset_hours))
  try:
    local_dt = datetime(
      *[int(p) for p in date_str.split('-')],
      hour, minute, tzinfo=tz,
    )
    return local_dt.astimezone(timezone.utc)
  except Exception:
    return None


def _eligible_windows(matches: list) -> list[tuple[datetime, str]]:
  """Return (kickoff, event_name) for every England/Scotland match, sorted by kickoff."""
  windows: list[tuple[datetime, str]] = []
  for m in matches:
    team1 = m.get("team1", "")
    team2 = m.get("team2", "")
    if team1 not in _ELIGIBLE_TEAMS and team2 not in _ELIGIBLE_TEAMS:
      continue
    kickoff = _parse_kickoff_utc(m.get("date", ""), m.get("time", ""))
    if kickoff is None:
      continue
    windows.append((kickoff, f"{team1} v {team2}"))
  windows.sort(key=lambda w: w[0])
  return windows


def _select_candidate(
  windows: list[tuple[datetime, str]],
  current: datetime,
) -> tuple[datetime | None, str | None]:
  """The earliest eligible match whose maximum (3h) window has not yet passed.

  We keep a match in play right through its potential extra-time window so a late ET
  confirmation can still extend it; whether it's actually 2h or 3h is decided later.
  """
  for kickoff, name in windows:
    if kickoff + _EXTRA_FREE_WINDOW > current:
      return kickoff, name
  return None, None


def _extra_time_check_required(
  start: datetime,
  current: datetime,
  already_extended: bool,
) -> bool:
  """True when we should consult the relay: in the [kickoff+88m, kickoff+3h) window
  and not already known to be extended."""
  if already_extended:
    return False
  return start + _EXTRA_TIME_CHECK_AFTER <= current < start + _EXTRA_FREE_WINDOW


def _resolve_window(
  windows: list[tuple[datetime, str]],
  current: datetime,
  already_extended: bool,
  already_extended_start: datetime | None,
  status: dict | None,
) -> tuple[datetime | None, datetime | None, str | None, bool]:
  """Pure decision: given the eligible windows, the current time, whether this match
  was already confirmed as extended, and a relay `status` (or None when it wasn't
  consulted / was unavailable), return (start, end, event_name, extended).

  Fallback rule: with no positive extra-time signal the window is the standard 2h.
  The relay only ever lengthens it.
  """
  start, name = _select_candidate(windows, current)
  if start is None:
    return None, None, None, False

  # Already decided as extra time for this same match — hold the 3h window.
  if already_extended and already_extended_start == start:
    return start, start + _EXTRA_FREE_WINDOW, name, True

  # Not yet in the extra-time check window: standard 2h (upcoming or early in the match).
  if current < start + _EXTRA_TIME_CHECK_AFTER:
    return start, start + _FREE_WINDOW, name, False

  # In the check window. Trust the relay's latched outcome when we have one.
  if status is not None:
    if status.get("extra_time"):
      return start, start + _EXTRA_FREE_WINDOW, name, True
    if status.get("match_finished"):
      # Finished in normal time — drop this match and advance to the next one (future,
      # so a standard 2h window with no relay call needed).
      later = [w for w in windows if w[0] > start]
      nxt_start, nxt_name = _select_candidate(later, current)
      if nxt_start is None:
        return None, None, None, False
      return nxt_start, nxt_start + _FREE_WINDOW, nxt_name, False

  # Undecided, or the relay was unavailable: keep the standard 2h window and retry.
  return start, start + _FREE_WINDOW, name, False


async def _async_fetch_extra_time(hass) -> dict | None:
  """Ask the relay whether the in-play match has gone to extra time.

  Returns {"extra_time": bool, "match_finished": bool} or None on ANY problem
  (unreachable, timeout, non-200, bad JSON). None means "no signal" — the caller
  falls back to the standard 2h window.
  """
  try:
    session = async_get_clientsession(hass)
    async with session.get(
      EXTRA_TIME_RELAY_URL,
      timeout=aiohttp.ClientTimeout(total=15),
    ) as response:
      if response.status != 200:
        _LOGGER.warning(f"Extra-time relay returned HTTP {response.status}; staying on 2h window")
        return None
      data = await response.json(content_type=None)
  except Exception as e:
    _LOGGER.warning(f"Extra-time relay unavailable ({e}); staying on 2h window")
    return None

  if not isinstance(data, dict):
    return None
  return {
    "extra_time": bool(data.get("extra_time", False)),
    "match_finished": bool(data.get("match_finished", False)),
  }


def _error_result(
  current: datetime,
  existing: EventFreeElectricityCoordinatorResult | None,
  error=None,
) -> EventFreeElectricityCoordinatorResult:
  if existing is not None:
    return EventFreeElectricityCoordinatorResult(
      existing.last_evaluated,
      existing.request_attempts + 1,
      existing.start,
      existing.end,
      existing.event_name,
      existing.extended,
      last_error=error,
    )
  return EventFreeElectricityCoordinatorResult(
    current - timedelta(minutes=REFRESH_RATE_IN_MINUTES_EVENT_FREE_ELECTRICITY),
    2, None, None, None, last_error=error,
  )


async def async_refresh_event_free_electricity(
  hass,
  current: datetime,
  existing: EventFreeElectricityCoordinatorResult | None,
) -> EventFreeElectricityCoordinatorResult:
  if existing is not None and current < existing.next_refresh:
    return existing

  try:
    session = async_get_clientsession(hass)
    async with session.get(
      _WORLDCUP_URL,
      timeout=aiohttp.ClientTimeout(total=30),
    ) as response:
      if response.status != 200:
        _LOGGER.warning(f"World Cup schedule returned HTTP {response.status}")
        return _error_result(current, existing)
      data = await response.json(content_type=None)
  except Exception as e:
    _LOGGER.warning(f"Failed to fetch World Cup schedule: {e}")
    return _error_result(current, existing, e)

  windows = _eligible_windows(data.get("matches", []))

  already_extended = existing is not None and existing.extended
  already_extended_start = existing.start if existing is not None else None

  # Only call the relay when an eligible match is actually in its extra-time window.
  status = None
  candidate_start, _ = _select_candidate(windows, current)
  if candidate_start is not None and _extra_time_check_required(
    candidate_start, current, already_extended and already_extended_start == candidate_start
  ):
    status = await _async_fetch_extra_time(hass)

  start, end, name, extended = _resolve_window(
    windows, current, already_extended, already_extended_start, status,
  )

  if start is not None:
    suffix = " (extended for extra time)" if extended else ""
    _LOGGER.debug(f"Eligible World Cup free window: {name}{suffix} {start} -> {end} UTC")
  else:
    _LOGGER.debug("No upcoming eligible World Cup matches found for England or Scotland")

  return EventFreeElectricityCoordinatorResult(current, 1, start, end, name, extended)


async def async_setup_event_free_electricity_coordinator(hass, account_id: str):
  key = DATA_EVENT_FREE_ELECTRICITY.format(account_id)
  coordinator_key = DATA_EVENT_FREE_ELECTRICITY_COORDINATOR.format(account_id)
  hass.data[DOMAIN][account_id][key] = None

  async def async_update():
    current = utcnow()
    existing = hass.data[DOMAIN][account_id].get(key)
    hass.data[DOMAIN][account_id][key] = await async_refresh_event_free_electricity(
      hass, current, existing,
    )
    return hass.data[DOMAIN][account_id][key]

  hass.data[DOMAIN][account_id][coordinator_key] = DataUpdateCoordinator(
    hass,
    _LOGGER,
    name=f"event_free_electricity_{account_id}",
    update_method=async_update,
    update_interval=timedelta(seconds=COORDINATOR_REFRESH_IN_SECONDS),
    always_update=True,
  )

  # Non-blocking — a fetch failure must not prevent the integration loading
  await hass.data[DOMAIN][account_id][coordinator_key].async_refresh()
