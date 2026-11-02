from datetime import datetime
import logging
import os
from homeassistant.helpers import storage
from homeassistant.util.dt import (parse_datetime)

from ..api_client.intelligent_dispatches import IntelligentDispatches
from ..const import MAX_INTELLIGENT_DISPATCH_HISTORY_FILE_SIZE_IN_BYTES

_LOGGER = logging.getLogger(__name__)

class IntelligentDispatchesHistoryItem:
  timestamp: datetime
  dispatches: IntelligentDispatches

  def __init__(self, timestamp: datetime, dispatches: IntelligentDispatches):
    self.timestamp = timestamp
    self.dispatches = dispatches

  def from_dict(data: dict):
    return IntelligentDispatchesHistoryItem(
      parse_datetime(data["timestamp"]),
      IntelligentDispatches.from_dict(data["dispatches"])
    )
  
  def to_dict(self):
    return {
      "timestamp": self.timestamp,
      "dispatches": self.dispatches.to_dict()
    }

class IntelligentDispatchesHistory:
  history: list[IntelligentDispatchesHistoryItem]

  def __init__(self, history: list[IntelligentDispatchesHistoryItem]):
    self.history = history

  def from_dict(data: dict):
    history = []
    for item in data["history"]:
      history.append(IntelligentDispatchesHistoryItem.from_dict(item))
    
    return IntelligentDispatchesHistory(history)
  
  def to_dict(self):
    return {
      "history": [item.to_dict() for item in self.history]
    }

def _get_file_size_in_bytes(path: str) -> int:
  try:
    return os.path.getsize(path)
  except OSError:
    return 0

async def async_load_cached_intelligent_dispatches_history(hass, device_id: str) -> IntelligentDispatchesHistory | None:
  key = f"edf_energy.intelligent_dispatches_history_{device_id}"
  store = storage.Store(hass, "1", key)

  # Versions between 18.4.0 and 18.9.6 stored a full copy of the completed dispatch list in every
  # history entry, which let this file reach gigabytes. Loading one of those is enough to exhaust
  # memory and take Home Assistant down, so check the size before we ever parse it.
  try:
    size_in_bytes = await hass.async_add_executor_job(_get_file_size_in_bytes, hass.config.path(".storage", key))
    if size_in_bytes > MAX_INTELLIGENT_DISPATCH_HISTORY_FILE_SIZE_IN_BYTES:
      _LOGGER.warning(
        f"Discarding intelligent dispatches history for {device_id} as it has grown to "
        f"{round(size_in_bytes / (1024 * 1024))}MB, which is too large to load safely. "
        "History will start again from now. This is a one off recovery from a bug in versions 18.4.0 to 18.9.6."
      )
      await store.async_remove()
      return IntelligentDispatchesHistory([])
  except Exception:
    _LOGGER.debug(f"Failed to check size of intelligent dispatches history for {device_id}")

  try:
    data = await store.async_load()
    if data is not None:
      _LOGGER.debug(f"Loaded cached intelligent dispatches history data for {device_id}")
      return IntelligentDispatchesHistory.from_dict(data)

    return IntelligentDispatchesHistory([])
  except:
    return IntelligentDispatchesHistory([])
  
async def async_save_cached_intelligent_dispatches_history(hass, device_id: str, intelligent_dispatches_history: IntelligentDispatchesHistory):
  if intelligent_dispatches_history is not None:
    store = storage.Store(hass, "1", f"edf_energy.intelligent_dispatches_history_{device_id}")
    await store.async_save(intelligent_dispatches_history.to_dict())
    _LOGGER.debug(f"Saved intelligent dispatches history data for ({device_id})")