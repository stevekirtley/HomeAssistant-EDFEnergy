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
  REFRESH_RATE_IN_MINUTES_EVENT_FREE_ELECTRICITY,
)
from . import BaseCoordinatorResult

_LOGGER = logging.getLogger(__name__)

_WORLDCUP_URL = "https://raw.githubusercontent.com/openfootball/worldcup.json/refs/heads/master/2026/worldcup.json"
_ELIGIBLE_TEAMS = {"England", "Scotland"}
_FREE_WINDOW = timedelta(hours=2)


class EventFreeElectricityCoordinatorResult(BaseCoordinatorResult):
  has_event: bool
  start: datetime | None
  end: datetime | None
  event_name: str | None

  def __init__(
    self,
    last_evaluated: datetime,
    request_attempts: int,
    start: datetime | None,
    end: datetime | None,
    event_name: str | None,
    last_error=None,
  ):
    super().__init__(last_evaluated, request_attempts, REFRESH_RATE_IN_MINUTES_EVENT_FREE_ELECTRICITY, None, last_error)
    self.start = start
    self.end = end
    self.event_name = event_name
    self.has_event = start is not None and end is not None
    # If an event window is active or upcoming, force a refresh shortly after it
    # ends so the sensors automatically advance to the next match.
    if self.has_event and end is not None and end < self.next_refresh:
      self.next_refresh = end + timedelta(minutes=1)


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


def _find_next_window(matches: list, current: datetime):
  """Return (start, end, event_name) for the active or next upcoming eligible match."""
  best = None
  for m in matches:
    team1 = m.get("team1", "")
    team2 = m.get("team2", "")
    if team1 not in _ELIGIBLE_TEAMS and team2 not in _ELIGIBLE_TEAMS:
      continue
    kickoff = _parse_kickoff_utc(m.get("date", ""), m.get("time", ""))
    if kickoff is None:
      continue
    window_end = kickoff + _FREE_WINDOW
    if window_end <= current:
      continue  # window already finished
    if best is None or kickoff < best[0]:
      best = (kickoff, window_end, f"{team1} v {team2}")
  return best if best is not None else (None, None, None)


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

  start, end, name = _find_next_window(data.get("matches", []), current)

  if start is not None:
    _LOGGER.debug(f"Next eligible World Cup match: {name} kicks off {start} UTC, window ends {end} UTC")
  else:
    _LOGGER.debug("No upcoming eligible World Cup matches found for England or Scotland")

  return EventFreeElectricityCoordinatorResult(current, 1, start, end, name)


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
