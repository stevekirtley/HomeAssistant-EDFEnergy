"""What we know about days the consumption statistics are short of.

Only the days EDF themselves could not supply are kept. Anything the integration was able to
fetch and fill is gone by the time this is written, so what remains is the list the user has
to take up with EDF.
"""
import logging
from homeassistant.helpers import storage

_LOGGER = logging.getLogger(__name__)

STORE_VERSION = "1"

def _store(hass, mpan: str, serial_number: str, is_export: bool):
  return storage.Store(
    hass, STORE_VERSION,
    f"edf_energy.consumption_gaps_{mpan}_{serial_number}{'_export' if is_export else ''}"
  )

async def async_load_consumption_gaps(hass, mpan: str, serial_number: str,
                                      is_export: bool) -> dict:
  try:
    data = await _store(hass, mpan, serial_number, is_export).async_load()
    if data is not None:
      return data
  except Exception:
    _LOGGER.debug(f"Could not read the consumption gap report for {mpan}/{serial_number}")

  return {"days": [], "last_checked": None}

async def async_save_consumption_gaps(hass, mpan: str, serial_number: str, is_export: bool,
                                      days: list, last_checked) -> None:
  await _store(hass, mpan, serial_number, is_export).async_save({
    "days": days,
    "last_checked": last_checked.isoformat() if last_checked is not None else None,
  })
  _LOGGER.debug(f"Saved consumption gap report for {mpan}/{serial_number} ({len(days)} days)")
