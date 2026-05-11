import logging
from datetime import datetime, timedelta
from homeassistant.helpers import storage
from homeassistant.util.dt import parse_datetime

_LOGGER = logging.getLogger(__name__)

class OffPeakWindowRecord:
  start: datetime
  end: datetime
  is_intelligent_adjusted: bool

  def __init__(self, start: datetime, end: datetime, is_intelligent_adjusted: bool):
    self.start = start
    self.end = end
    self.is_intelligent_adjusted = is_intelligent_adjusted

  def from_dict(data: dict):
    return OffPeakWindowRecord(
      parse_datetime(data["start"]),
      parse_datetime(data["end"]),
      data.get("is_intelligent_adjusted", False)
    )

  def to_dict(self):
    return {
      "start": self.start,
      "end": self.end,
      "is_intelligent_adjusted": self.is_intelligent_adjusted,
    }

def merge_off_peak_windows(existing: list, new_windows: list, current: datetime) -> list:
  """Merge new windows into existing, dedup by (start, end), purge older than 60 days."""
  min_time = (current - timedelta(days=60)).replace(hour=0, minute=0, second=0, microsecond=0)
  seen = {}

  for w in [*existing, *new_windows]:
    key = (w.start, w.end)
    # Prefer the intelligent-adjusted record when there's a clash — it carries more information
    if key not in seen or w.is_intelligent_adjusted:
      seen[key] = w

  return sorted(
    [w for w in seen.values() if w.start >= min_time],
    key=lambda w: w.start
  )

async def async_load_cached_off_peak_history(hass, mpan: str, serial_number: str) -> list:
  store = storage.Store(hass, "1", f"edf_energy.off_peak_history_{mpan}_{serial_number}")
  try:
    data = await store.async_load()
    if data is not None:
      _LOGGER.debug(f"Loaded off-peak history for {mpan}/{serial_number}")
      return [OffPeakWindowRecord.from_dict(item) for item in data.get("windows", [])]
  except Exception:
    pass
  return []

async def async_save_cached_off_peak_history(hass, mpan: str, serial_number: str, windows: list):
  store = storage.Store(hass, "1", f"edf_energy.off_peak_history_{mpan}_{serial_number}")
  await store.async_save({"windows": [w.to_dict() for w in windows]})
  _LOGGER.debug(f"Saved off-peak history for {mpan}/{serial_number} ({len(windows)} windows)")
