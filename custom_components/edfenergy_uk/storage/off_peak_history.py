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

  Only inside the span the rates cover, though. That is the only place the rates say anything
  about what replaced what, so it is the only place a clip is a correction rather than a guess.
  Clipping used to run over the whole sixty days on every refresh and save the result, and
  history written before #49 was fixed is full of re-planned windows overlapping each other.
  The clip dropped every one of those that shared a start and cut the survivor off at the next
  window along, so weeks of smart charging windows were rewritten into shorter ones that never
  happened, and the store was overwritten with them.
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

  return clip_overlapping_windows(windows, in_span)

def clip_overlapping_windows(windows: list, may_clip=lambda window: True) -> list:
  """Pull back any window that runs into the start of the one after it.

  Overlaps come from a dispatch being reshaped while it was running: the record of what had
  been planned reaches past the point where the replacement takes over. A window left with
  nothing of itself after clipping is dropped.

  A window is only clipped against the next when may_clip holds for both of them. Anything
  else is left exactly as it is, overlap and all, because dropping or shortening a record is
  not something that can be undone once the store has been written.
  """
  clipped = []

  for index, window in enumerate(windows):
    end = window.end
    if (index + 1 < len(windows)
        and end > windows[index + 1].start
        and may_clip(window)
        and may_clip(windows[index + 1])):
      end = windows[index + 1].start

    if end > window.start:
      clipped.append(OffPeakWindowRecord(window.start, end, window.is_intelligent_adjusted))

  return clipped

def _union(intervals: list) -> list:
  merged = []
  for start, end in sorted(intervals):
    if merged and start <= merged[-1][1]:
      merged[-1] = (merged[-1][0], max(merged[-1][1], end))
    else:
      merged.append((start, end))
  return merged

def _subtract(intervals: list, taken: list) -> list:
  """What is left of each interval once everything in taken is cut out of it."""
  remaining = []
  for start, end in intervals:
    pieces = [(start, end)]
    for taken_start, taken_end in taken:
      pieces = [
        piece
        for piece_start, piece_end in pieces
        for piece in (
          [(piece_start, piece_end)] if taken_end <= piece_start or taken_start >= piece_end
          else [(piece_start, taken_start), (taken_end, piece_end)]
        )
        if piece[1] > piece[0]
      ]
    remaining.extend(pieces)
  return remaining

def rebuild_from_started_dispatches(history: list, started: list, before: datetime) -> tuple[list, int]:
  """Put back smart charging windows the 21.0.0 clip took out, from the dispatches that ran.

  The clip rewrote stored history and saved it, so the windows it dropped are gone from this
  store. The started dispatches are a separate record of what actually charged, kept for the
  same sixty days and never touched by the clip, so the part of a lost window that really ran
  can be worked out again: whatever a started dispatch covers that no stored window already
  does.

  This only ever adds. Nothing already in the history is changed or taken out, and nothing is
  added that a dispatch did not run - a window EDF planned and then revoked is not put back,
  because it never happened. Only time before `before` is considered, so today and anything
  the rates still cover is left to them, and only time from the first stored window on, so a
  sensor that started recording recently does not suddenly gain weeks it never saw.

  Returns the history with the added windows, and how many were added.
  """
  if not history or not started:
    return history, 0

  earliest = min(window.start for window in history)
  ran = _union([
    (max(dispatch.start, earliest), min(dispatch.end, before))
    for dispatch in started
    if dispatch.start is not None and dispatch.end is not None
       and dispatch.end > earliest and dispatch.start < before
  ])
  covered = _union([(window.start, window.end) for window in history])

  added = [
    OffPeakWindowRecord(start, end, True)
    for start, end in _subtract(ran, covered)
  ]
  if not added:
    return history, 0

  return sorted([*history, *added], key=lambda window: window.start), len(added)

def _off_peak_history_store(hass, mpan: str, serial_number: str):
  return storage.Store(hass, "1", f"edf_energy.off_peak_history_{mpan}_{serial_number}")

async def async_load_off_peak_history_store(hass, mpan: str, serial_number: str) -> tuple[list, bool]:
  """The stored windows, and whether the dispatch repair has already been run on them."""
  try:
    data = await _off_peak_history_store(hass, mpan, serial_number).async_load()
    if data is not None:
      _LOGGER.debug(f"Loaded off-peak history for {mpan}/{serial_number}")
      return (
        [OffPeakWindowRecord.from_dict(item) for item in data.get("windows", [])],
        data.get("dispatch_repair") == 1,
      )
  except Exception:
    pass
  return [], False

async def async_load_cached_off_peak_history(hass, mpan: str, serial_number: str) -> list:
  windows, _ = await async_load_off_peak_history_store(hass, mpan, serial_number)
  return windows

async def async_save_cached_off_peak_history(hass, mpan: str, serial_number: str, windows: list,
                                             dispatch_repair_done: bool = False):
  data = {"windows": [w.to_dict() for w in windows]}
  # Kept on every save once it is set. Dropping it would only make the repair run again, which
  # adds nothing the second time, but there is no reason to have it look every restart.
  if dispatch_repair_done:
    data["dispatch_repair"] = 1
  await _off_peak_history_store(hass, mpan, serial_number).async_save(data)
  _LOGGER.debug(f"Saved off-peak history for {mpan}/{serial_number} ({len(windows)} windows)")
