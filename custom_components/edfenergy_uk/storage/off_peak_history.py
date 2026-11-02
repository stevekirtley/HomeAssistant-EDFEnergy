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

def merge_off_peak_windows(existing: list, new_windows: list, current: datetime,
                           span_start: datetime | None = None,
                           span_end: datetime | None = None) -> list:
  """Merge new windows into existing, dedup by (start, end), purge older than 60 days.

  A window that has already started is history and is kept whatever the rates say later.
  A window that has not started yet is a forecast, and forecasts change: a smart charging
  plan is written in here as soon as EDF publish it, and EDF revoke and reshape plans
  through the day. So anything still in the future is taken from the new windows rather
  than remembered - an existing record that the rates no longer carry is dropped.

  That is only safe where the new windows actually have something to say, which is why
  the span the rates cover has to be passed in to do it. Without it the old behaviour is
  kept and nothing is dropped, because a refresh holding only today's rates must not be
  read as tomorrow's windows having been revoked.

  A dispatch that was reshaped after it began is not simply remembered. Where the rates still
  carry a window starting at the same moment, that is the same dispatch re-planned, and the
  new shape replaces the old - keeping both left the list showing a window that ran to a
  length it never reached, overlapping the one that replaced it (issue #49).

  Where a window that ran is followed by one that overlaps it, the earlier one is clipped back
  to where the later one begins. The part before the change happened; the part after did not.
  """
  min_time = (current - timedelta(days=60)).replace(hour=0, minute=0, second=0, microsecond=0)
  know_span = span_start is not None and span_end is not None
  new_keys = {(w.start, w.end) for w in new_windows}
  new_starts = {w.start for w in new_windows}

  def in_span(window) -> bool:
    return know_span and span_start <= window.start < span_end

  def superseded(window) -> bool:
    """A forecast the rates no longer carry. It never ran, so it goes."""
    return (window.start > current
            and in_span(window)
            and (window.start, window.end) not in new_keys)

  def reshaped(window) -> bool:
    """The rates still start a window here but finish it somewhere else, so this is the same
    dispatch re-planned rather than one we are remembering. True whether or not it has begun,
    which is the case the first attempt at this missed."""
    return (in_span(window)
            and (window.start, window.end) not in new_keys
            and window.start in new_starts)

  seen = {}

  for w in [*[w for w in existing if not superseded(w) and not reshaped(w)], *new_windows]:
    key = (w.start, w.end)
    # Prefer the intelligent-adjusted record when there's a clash — it carries more information
    if key not in seen or w.is_intelligent_adjusted:
      seen[key] = w

  windows = sorted(
    [w for w in seen.values() if w.start >= min_time],
    key=lambda w: w.start
  )

  return clip_overlapping_windows(windows)

def clip_overlapping_windows(windows: list) -> list:
  """Pull back any window that runs into the start of the one after it.

  Overlaps come from a dispatch being reshaped while it was running: the record of what had
  been planned reaches past the point where the replacement takes over. A window left with
  nothing of itself after clipping is dropped.
  """
  clipped = []

  for index, window in enumerate(windows):
    end = window.end
    if index + 1 < len(windows) and end > windows[index + 1].start:
      end = windows[index + 1].start

    if end > window.start:
      clipped.append(OffPeakWindowRecord(window.start, end, window.is_intelligent_adjusted))

  return clipped

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
