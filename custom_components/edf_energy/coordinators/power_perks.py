"""Coordinator for EDF Power Perks free electricity sessions.

EDF announce Power Perks sessions by SMS the day before (occasionally the same day) and
nowhere else - not in the Kraken API, not in their website APIs, and not in the mobile app,
whose Power Perks screen is a fixed "free electricity is auto-applied when available"
banner. The text is therefore relayed from the phone to a small endpoint that parses it
and publishes the sessions as JSON (see tools/power_perks_relay). This coordinator
polls that feed and hands the sessions to the free electricity sessions coordinator, where
they join the calendar, the session sensors and the events feed like any other source.

A session can also be registered by hand through the register_power_perks_session action,
for a text the relay could not parse or for anyone who does not want to use the relay.
"""
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import aiohttp
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util.dt import as_utc, parse_datetime, utcnow

from ..api_client import user_agent_value
from ..api_client.free_electricity_sessions import FreeElectricitySession
from ..const import (
  COORDINATOR_REFRESH_IN_SECONDS,
  INTEGRATION_VERSION,
  DATA_POWER_PERKS,
  DATA_POWER_PERKS_COORDINATOR,
  DATA_POWER_PERKS_MANUAL_SESSIONS,
  DOMAIN,
  POWER_PERKS_FEED_URL,
  REFRESH_RATE_IN_MINUTES_POWER_PERKS,
)
from . import BaseCoordinatorResult

_LOGGER = logging.getLogger(__name__)

SOURCE = "power_perks"
_UK_TZ = ZoneInfo("Europe/London")


class PowerPerksCoordinatorResult(BaseCoordinatorResult):
  """Sessions from the relay feed, plus any registered by hand on this instance."""

  sessions: list[FreeElectricitySession]
  manual_sessions: list[FreeElectricitySession]
  feed_available: bool

  def __init__(
    self,
    last_evaluated: datetime,
    request_attempts: int,
    sessions: list[FreeElectricitySession],
    manual_sessions: list[FreeElectricitySession] | None = None,
    feed_available: bool = True,
    last_error=None,
  ):
    super().__init__(last_evaluated, request_attempts, REFRESH_RATE_IN_MINUTES_POWER_PERKS, None, last_error)
    self.sessions = sessions
    self.manual_sessions = manual_sessions or []
    self.feed_available = feed_available

  @property
  def all_sessions(self) -> list[FreeElectricitySession]:
    """Feed and manual sessions together, one per code, manual winning on a clash."""
    by_code = {s.code: s for s in self.sessions}
    for session in self.manual_sessions:
      by_code[session.code] = session
    return sorted(by_code.values(), key=lambda s: s.start)


def _parse_session_datetime(value) -> datetime | None:
  """A feed timestamp as UTC. The relay publishes UK offsets; a bare timestamp is read as UK time."""
  if not isinstance(value, str):
    return None
  parsed = parse_datetime(value)
  if parsed is None:
    return None
  if parsed.tzinfo is None:
    parsed = parsed.replace(tzinfo=_UK_TZ)
  return as_utc(parsed)


def session_code(start: datetime) -> str:
  """The code for a session starting at the given time - the same one the relay uses."""
  return f"{SOURCE}_{start.astimezone(_UK_TZ).strftime('%Y%m%d%H%M')}"


def make_power_perks_session(start: datetime, end: datetime) -> FreeElectricitySession:
  return FreeElectricitySession(session_code(start), as_utc(start), as_utc(end), SOURCE)


def parse_power_perks_feed(data) -> list[FreeElectricitySession] | None:
  """Turn the relay's JSON into sessions.

  Returns None if the payload is not the feed at all (so the caller keeps what it had), or
  a list - possibly empty - of the well-formed sessions in it. A malformed entry is skipped
  and logged rather than failing the whole feed.
  """
  if not isinstance(data, dict) or not isinstance(data.get("sessions"), list):
    return None

  sessions: list[FreeElectricitySession] = []
  for entry in data["sessions"]:
    if not isinstance(entry, dict):
      continue
    start = _parse_session_datetime(entry.get("start"))
    end = _parse_session_datetime(entry.get("end"))
    if start is None or end is None or end <= start:
      _LOGGER.warning("Skipping malformed Power Perks session from feed: %s", str(entry)[:200])
      continue
    code = entry.get("code") if isinstance(entry.get("code"), str) and entry.get("code") else session_code(start)
    sessions.append(FreeElectricitySession(code, start, end, SOURCE))

  sessions.sort(key=lambda s: s.start)
  return sessions


async def async_fetch_power_perks_feed(hass) -> dict | None:
  """Fetch the relay feed. None on any problem - the caller keeps the last known sessions."""
  try:
    session = async_get_clientsession(hass)
    # The relay serves the feed to this integration, identified by its user agent.
    headers = {"User-Agent": f"{user_agent_value}/{INTEGRATION_VERSION}"}
    async with session.get(POWER_PERKS_FEED_URL, headers=headers, timeout=aiohttp.ClientTimeout(total=20)) as response:
      if response.status != 200:
        _LOGGER.warning("Power Perks feed returned HTTP %s; keeping last known sessions", response.status)
        return None
      return await response.json(content_type=None)
  except Exception as e:
    _LOGGER.warning("Power Perks feed unavailable (%s); keeping last known sessions", e)
    return None


async def async_refresh_power_perks(
  current: datetime,
  fetch_feed,
  manual_sessions: list[FreeElectricitySession],
  existing_result: PowerPerksCoordinatorResult | None,
) -> PowerPerksCoordinatorResult:
  if existing_result is not None and current < existing_result.next_refresh:
    # Manual registrations must show up straight away, without waiting for the next poll.
    if existing_result.manual_sessions != manual_sessions:
      return PowerPerksCoordinatorResult(
        existing_result.last_evaluated,
        existing_result.request_attempts,
        existing_result.sessions,
        manual_sessions,
        existing_result.feed_available,
        existing_result.last_error,
      )
    return existing_result

  data = await fetch_feed()
  sessions = parse_power_perks_feed(data) if data is not None else None

  if sessions is None:
    previous = existing_result.sessions if existing_result is not None else []
    attempts = existing_result.request_attempts + 1 if existing_result is not None else 1
    if data is not None:
      _LOGGER.warning("Power Perks feed payload was not recognised; keeping last known sessions")
    return PowerPerksCoordinatorResult(
      current - timedelta(minutes=REFRESH_RATE_IN_MINUTES_POWER_PERKS) + timedelta(minutes=min(5 * attempts, REFRESH_RATE_IN_MINUTES_POWER_PERKS)),
      attempts,
      previous,
      manual_sessions,
      feed_available=False,
      last_error=Exception("Power Perks feed unavailable"),
    )

  _LOGGER.debug("Power Perks feed returned %d session(s)", len(sessions))
  return PowerPerksCoordinatorResult(current, 1, sessions, manual_sessions, feed_available=True)


def register_manual_session(hass, account_id: str, start: datetime, end: datetime) -> FreeElectricitySession:
  """Record a hand-entered session for an account. Re-registering the same start replaces it."""
  key = DATA_POWER_PERKS_MANUAL_SESSIONS.format(account_id)
  session = make_power_perks_session(start, end)
  existing = [s for s in (hass.data[DOMAIN][account_id].get(key) or []) if s.code != session.code]
  existing.append(session)
  existing.sort(key=lambda s: s.start)
  hass.data[DOMAIN][account_id][key] = existing
  return session


async def async_setup_power_perks_coordinator(hass, account_id: str, entry):
  key = DATA_POWER_PERKS.format(account_id)
  coordinator_key = DATA_POWER_PERKS_COORDINATOR.format(account_id)
  hass.data[DOMAIN][account_id].setdefault(DATA_POWER_PERKS_MANUAL_SESSIONS.format(account_id), [])

  async def async_update():
    current = utcnow()
    existing = hass.data[DOMAIN][account_id].get(key)
    manual = list(hass.data[DOMAIN][account_id].get(DATA_POWER_PERKS_MANUAL_SESSIONS.format(account_id)) or [])
    result = await async_refresh_power_perks(current, lambda: async_fetch_power_perks_feed(hass), manual, existing)
    hass.data[DOMAIN][account_id][key] = result
    return result

  hass.data[DOMAIN][account_id][coordinator_key] = DataUpdateCoordinator(
    hass,
    _LOGGER,
    name=f"power_perks_{account_id}",
    update_method=async_update,
    update_interval=timedelta(seconds=COORDINATOR_REFRESH_IN_SECONDS),
    always_update=True,
  )

  # A feed failure must never stop the integration loading.
  await hass.data[DOMAIN][account_id][coordinator_key].async_refresh()
