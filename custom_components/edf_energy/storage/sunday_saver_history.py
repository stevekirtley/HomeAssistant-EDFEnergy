import logging
from datetime import datetime, timedelta
from homeassistant.helpers import storage
from homeassistant.util.dt import parse_datetime

_LOGGER = logging.getLogger(__name__)


class SundaySaverWindowRecord:
  start: datetime
  end: datetime
  free_hours: float

  def __init__(self, start: datetime, end: datetime, free_hours: float):
    self.start = start
    self.end = end
    self.free_hours = free_hours

  def from_dict(data: dict):
    return SundaySaverWindowRecord(
      parse_datetime(data["start"]),
      parse_datetime(data["end"]),
      float(data.get("free_hours", 0)),
    )

  def to_dict(self):
    return {
      "start": self.start,
      "end": self.end,
      "free_hours": self.free_hours,
    }


def merge_sunday_saver_windows(existing: list, new_windows: list, current: datetime) -> list:
  """Merge new windows into existing, dedup by (start, end), purge older than 60 days."""
  min_time = (current - timedelta(days=60)).replace(hour=0, minute=0, second=0, microsecond=0)
  seen = {}
  for w in [*existing, *new_windows]:
    key = (w.start, w.end)
    if key not in seen:
      seen[key] = w
  return sorted(
    [w for w in seen.values() if w.start >= min_time],
    key=lambda w: w.start,
  )


async def async_load_cached_sunday_saver_history(hass, account_id: str) -> list:
  store = storage.Store(hass, "1", f"edf_energy.sunday_saver_history_{account_id}")
  try:
    data = await store.async_load()
    if data is not None:
      _LOGGER.debug(f"Loaded Sunday Saver history for account {account_id}")
      return [SundaySaverWindowRecord.from_dict(item) for item in data.get("windows", [])]
  except Exception:
    pass
  return []


async def async_save_cached_sunday_saver_history(hass, account_id: str, windows: list):
  store = storage.Store(hass, "1", f"edf_energy.sunday_saver_history_{account_id}")
  await store.async_save({"windows": [w.to_dict() for w in windows]})
  _LOGGER.debug(f"Saved Sunday Saver history for account {account_id} ({len(windows)} windows)")
