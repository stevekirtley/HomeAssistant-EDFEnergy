import logging
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
  RELAY_FIXTURES_URL,
  REFRESH_RATE_IN_MINUTES_EVENT_FREE_ELECTRICITY,
)
from . import BaseCoordinatorResult

_LOGGER = logging.getLogger(__name__)

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
  et_start: datetime | None
  et_end: datetime | None

  def __init__(
    self,
    last_evaluated: datetime,
    request_attempts: int,
    start: datetime | None,
    end: datetime | None,
    event_name: str | None,
    et_start: datetime | None = None,
    et_end: datetime | None = None,
    last_error=None,
  ):
    super().__init__(last_evaluated, request_attempts, REFRESH_RATE_IN_MINUTES_EVENT_FREE_ELECTRICITY, None, last_error)
    self.start = start
    self.end = end
    self.event_name = event_name
    self.et_start = et_start
    self.et_end = et_end
    self.has_event = start is not None and end is not None

    # Tighten the refresh cadence around a match so we (a) wake up in time to start
    # checking for extra time, (b) poll every 2 min while undecided, and (c) advance
    # to the next match once the window(s) end.
    if self.has_event:
      current = last_evaluated
      check_start = start + _EXTRA_TIME_CHECK_AFTER

      if et_start is None:
        # ET not yet confirmed — wake up at the check window start, then poll every 2 min.
        if current < check_start:
          self.next_refresh = min(self.next_refresh, check_start)
        elif current < start + _EXTRA_FREE_WINDOW:
          self.next_refresh = min(self.next_refresh, current + _EXTRA_TIME_POLL)

      # Wake up just after the main session ends.
      after_main = end + timedelta(minutes=1)
      if current < after_main:
        self.next_refresh = min(self.next_refresh, after_main)

      # If ET confirmed, also wake up just after the ET session ends.
      if et_end is not None:
        after_et = et_end + timedelta(minutes=1)
        if current < after_et:
          self.next_refresh = min(self.next_refresh, after_et)


def _eligible_windows(fixtures: list) -> list[tuple[datetime, str, bool]]:
  """Return (kickoff, event_name, is_knockout) for all relay fixtures, sorted by kickoff."""
  windows: list[tuple[datetime, str, bool]] = []
  for f in fixtures:
    ts = f.get("timestamp")
    if ts is None:
      continue
    try:
      kickoff = datetime.fromtimestamp(int(ts), tz=timezone.utc)
    except Exception:
      continue
    home = f.get("home", "")
    away = f.get("away", "")
    is_knockout = f.get("round", "group-stage") != "group-stage"
    windows.append((kickoff, f"{home} v {away}", is_knockout))
  windows.sort(key=lambda w: w[0])
  return windows


def _select_candidate(
  windows: list[tuple[datetime, str, bool]],
  current: datetime,
) -> tuple[datetime | None, str | None, bool]:
  """The earliest eligible match whose maximum window has not yet passed.

  Knockout matches are kept alive for 3h (to allow a late ET confirmation); group
  stage matches expire after the standard 2h since extra time is impossible.
  """
  for kickoff, name, is_knockout in windows:
    max_window = _EXTRA_FREE_WINDOW if is_knockout else _FREE_WINDOW
    if kickoff + max_window > current:
      return kickoff, name, is_knockout
  return None, None, False


def _extra_time_check_required(
  start: datetime,
  current: datetime,
  already_et: bool,
  is_knockout: bool = False,
) -> bool:
  """True when we should consult the relay: knockout match, in the [kickoff+88m, kickoff+3h)
  window, and ET not already confirmed."""
  if not is_knockout:
    return False
  if already_et:
    return False
  return start + _EXTRA_TIME_CHECK_AFTER <= current < start + _EXTRA_FREE_WINDOW


def _resolve_window(
  windows: list[tuple[datetime, str, bool]],
  current: datetime,
  already_et_start: datetime | None,
  status: dict | None,
) -> tuple[datetime | None, datetime | None, str | None, datetime | None, datetime | None]:
  """Return (start, end, event_name, et_start, et_end).

  The main session is always kickoff → kickoff+2h. When extra time is confirmed a
  separate ET session (kickoff+2h → kickoff+3h) is returned alongside it — both
  are surfaced as distinct free electricity slots rather than one extended window.

  Fallback: without a positive ET signal the main session stays at 2h and et_start
  is None.
  """
  start, name, is_knockout = _select_candidate(windows, current)
  if start is None:
    return None, None, None, None, None

  # ET already confirmed for this match — keep both sessions.
  if already_et_start is not None and already_et_start == start:
    return start, start + _FREE_WINDOW, name, start + _FREE_WINDOW, start + _EXTRA_FREE_WINDOW

  # Group stage: no ET possible.
  if not is_knockout:
    return start, start + _FREE_WINDOW, name, None, None

  # Before the check window: main session only.
  if current < start + _EXTRA_TIME_CHECK_AFTER:
    return start, start + _FREE_WINDOW, name, None, None

  # In the check window — use the relay's latched verdict.
  if status is not None:
    if status.get("extra_time"):
      return start, start + _FREE_WINDOW, name, start + _FREE_WINDOW, start + _EXTRA_FREE_WINDOW
    if status.get("match_finished"):
      # Finished in normal time — advance to the next scheduled match.
      later = [w for w in windows if w[0] > start]
      nxt_start, nxt_name, _ = _select_candidate(later, current)
      if nxt_start is None:
        return None, None, None, None, None
      return nxt_start, nxt_start + _FREE_WINDOW, nxt_name, None, None

  # Undecided or relay unavailable — main session only, retry shortly.
  return start, start + _FREE_WINDOW, name, None, None


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
      existing.et_start,
      existing.et_end,
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
      RELAY_FIXTURES_URL,
      timeout=aiohttp.ClientTimeout(total=30),
    ) as response:
      if response.status != 200:
        _LOGGER.warning(f"Relay fixtures returned HTTP {response.status}")
        return _error_result(current, existing)
      data = await response.json(content_type=None)
  except Exception as e:
    _LOGGER.warning(f"Failed to fetch relay fixtures: {e}")
    return _error_result(current, existing, e)

  if not isinstance(data, dict) or not data.get("ok"):
    _LOGGER.warning("Relay fixtures response was not OK")
    return _error_result(current, existing)

  windows = _eligible_windows(data.get("fixtures", []))

  already_et_start = existing.et_start if existing is not None else None

  # Only call the relay when an eligible match is in its check window and ET not yet confirmed.
  status = None
  candidate_start, _, candidate_is_knockout = _select_candidate(windows, current)
  if candidate_start is not None and _extra_time_check_required(
    candidate_start, current,
    already_et_start is not None and already_et_start == candidate_start,
    candidate_is_knockout,
  ):
    status = await _async_fetch_extra_time(hass)

  start, end, name, et_start, et_end = _resolve_window(
    windows, current, already_et_start, status,
  )

  if start is not None:
    if et_start is not None:
      _LOGGER.debug(f"World Cup free window: {name} {start} -> {end} UTC + ET bonus {et_start} -> {et_end} UTC")
    else:
      _LOGGER.debug(f"World Cup free window: {name} {start} -> {end} UTC")
  else:
    _LOGGER.debug("No upcoming World Cup fixtures found")

  return EventFreeElectricityCoordinatorResult(current, 1, start, end, name, et_start, et_end)


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
