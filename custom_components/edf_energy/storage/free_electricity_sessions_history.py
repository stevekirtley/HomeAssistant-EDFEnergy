import logging
from datetime import datetime, timedelta
from homeassistant.helpers import storage
from homeassistant.util.dt import parse_datetime, as_local

from ..api_client.free_electricity_sessions import FreeElectricitySession

_LOGGER = logging.getLogger(__name__)

# Sessions are retained for 60 days to match the Sunday Saver and off-peak history stores. Only
# today's sessions are ever republished to the events feed (see refresh_free_electricity_sessions),
# so this history is really here to survive a HA restart and to back a future panel history card.
_RETENTION_DAYS = 60


def session_to_dict(session: FreeElectricitySession) -> dict:
  return {
    "code": session.code,
    "start": session.start,
    "end": session.end,
    "source": session.source,
  }


def session_from_dict(data: dict) -> FreeElectricitySession:
  return FreeElectricitySession(
    data["code"],
    parse_datetime(data["start"]),
    parse_datetime(data["end"]),
    data.get("source"),
  )


def session_to_window(session: FreeElectricitySession) -> dict:
  """The panel-facing shape for a session, with local times, used for the history card attribute."""
  return {
    "code": session.code,
    "source": session.source,
    "start": as_local(session.start),
    "end": as_local(session.end),
    "duration_in_minutes": session.duration_in_minutes,
  }


def merge_free_electricity_sessions(
  existing: list[FreeElectricitySession],
  new_sessions: list[FreeElectricitySession],
  current: datetime,
) -> list[FreeElectricitySession]:
  """Merge new sessions into existing history, dedup by code, purge sessions older than 60 days.

  New sessions win on a code collision so that any late refinement of a window (e.g. a knockout
  match whose end shifts once extra time is confirmed) replaces the earlier record.
  """
  min_time = (current - timedelta(days=_RETENTION_DAYS)).replace(hour=0, minute=0, second=0, microsecond=0)
  by_code: dict[str, FreeElectricitySession] = {}
  for session in existing:
    by_code[session.code] = session
  for session in new_sessions:
    by_code[session.code] = session
  return sorted(
    [s for s in by_code.values() if s.end >= min_time],
    key=lambda s: s.start,
  )


async def async_load_cached_free_electricity_sessions_history(hass, account_id: str) -> list[FreeElectricitySession]:
  store = storage.Store(hass, "1", f"edf_energy.free_electricity_sessions_history_{account_id}")
  try:
    data = await store.async_load()
    if data is not None:
      _LOGGER.debug(f"Loaded free electricity sessions history for account {account_id}")
      return [session_from_dict(item) for item in data.get("sessions", [])]
  except Exception:
    pass
  return []


async def async_save_cached_free_electricity_sessions_history(hass, account_id: str, sessions: list[FreeElectricitySession]):
  store = storage.Store(hass, "1", f"edf_energy.free_electricity_sessions_history_{account_id}")
  await store.async_save({"sessions": [session_to_dict(s) for s in sessions]})
  _LOGGER.debug(f"Saved free electricity sessions history for account {account_id} ({len(sessions)} sessions)")
