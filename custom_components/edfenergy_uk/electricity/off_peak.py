from datetime import timedelta
import logging

from homeassistant.const import (
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import generate_entity_id

from homeassistant.util.dt import (now, start_of_local_day)
from homeassistant.helpers.update_coordinator import (
  CoordinatorEntity
)
from homeassistant.components.binary_sensor import (
    BinarySensorEntity
)
from homeassistant.helpers.restore_state import RestoreEntity

from ..utils import get_off_peak_times, get_off_peak_windows_from_rates, is_off_peak
from ..storage.off_peak_history import (
  OffPeakWindowRecord,
  merge_off_peak_windows,
  rebuild_from_started_dispatches,
  async_load_off_peak_history_store,
  async_save_cached_off_peak_history,
)
from ..storage.intelligent_dispatches import async_load_cached_intelligent_dispatches

from .base import EDFEnergyElectricitySensor
from ..utils.attributes import dict_to_typed_dict

_LOGGER = logging.getLogger(__name__)

# How many days of off-peak windows to expose in the attribute. History is retained for 60 days
# (see merge_off_peak_windows) but the attribute drives the date picker on the panel/card, so we
# only surface a recent slice. 21 days (~22 dates) stays comfortably under HA's ~16KB attribute
# size limit - 30 days measured ~18KB on real data because intelligent tariffs fragment the
# window into many pieces on some days.
OFF_PEAK_ATTRIBUTE_RETENTION_DAYS = 21

class EDFEnergyElectricityOffPeak(CoordinatorEntity, EDFEnergyElectricitySensor, BinarySensorEntity, RestoreEntity):
  """Sensor for determining if the current rate is off peak."""

  def __init__(self, hass: HomeAssistant, coordinator, meter, point, account_id: str | None = None,
               intelligent_device_ids: list | None = None):
    """Init sensor."""

    CoordinatorEntity.__init__(self, coordinator)
    EDFEnergyElectricitySensor.__init__(self, hass, meter, point)
  
    self._state = None
    self._attributes = {
      "current_start": None,
      "current_end": None,
      "next_start": None,
      "next_end": None,
      "off_peak_windows": [],
    }
    self._off_peak_history: list[OffPeakWindowRecord] = []
    self._last_updated = None
    # Only what is needed to repair the history once, at startup. See _async_repair_from_dispatches.
    self._account_id = account_id
    self._intelligent_device_ids = list(intelligent_device_ids or [])
    self._dispatch_repair_done = False

    self.entity_id = generate_entity_id("binary_sensor.{}", self.unique_id, hass=hass)

  @property
  def unique_id(self):
    """The id of the sensor."""
    return f"edf_energy_electricity_{self._serial_number}_{self._mpan}{self._export_id_addition}_off_peak"
    
  @property
  def name(self):
    """Name of the sensor."""
    return f"Off Peak {self._export_name_addition}Electricity ({self._serial_number}/{self._mpan})"

  @property
  def icon(self):
    """Icon of the sensor."""
    return "mdi:lightning-bolt"

  @property
  def extra_state_attributes(self):
    """Attributes of the sensor."""
    return self._attributes

  @property
  def is_on(self):
    return self._state
  
  @callback
  def _handle_coordinator_update(self) -> None:
    """Determine if current rate is off peak."""
    current = now()
    rates = self.coordinator.data.rates if self.coordinator is not None and self.coordinator.data is not None else None
    if (rates is not None):
      _LOGGER.debug(f"Updating EDFEnergyElectricityOffPeak for '{self._mpan}/{self._serial_number}'")

      self._state = False
      self._attributes = {
        "current_start": None,
        "current_end": None,
        "next_start": None,
        "next_end": None,
      }
      
      times = get_off_peak_times(current, rates, True)
      _LOGGER.debug(f"Calculated off-peak times for '{self._mpan}/{self._serial_number}': {[time.to_dict() for time in times]}")
      if times is not None and len(times) > 0:
        time = times.pop(0)
        if time.start <= current:
          self._attributes["current_start"] = time.start
          self._attributes["current_end"] = time.end
          self._state = True

          if len(times) > 0:
            self._attributes["next_start"] = times[0].start
            self._attributes["next_end"] = times[0].end
        else:
          self._attributes["next_start"] = time.start
          self._attributes["next_end"] = time.end

      # Accumulate off-peak windows from the current rates data. The span these rates cover
      # is passed along so that windows inside it which are still to come can be corrected
      # rather than accumulated - EDF revoke and reshape smart charging plans through the
      # day, and a plan that no longer stands is not history.
      new_windows = [
        OffPeakWindowRecord(w["start"], w["end"], w["is_intelligent_adjusted"])
        for w in get_off_peak_windows_from_rates(rates)
      ]
      # An empty rate list says nothing about any window, so the span is withheld and the
      # history is left exactly as it is rather than being read as everything revoked.
      self._off_peak_history = merge_off_peak_windows(
        self._off_peak_history, new_windows, current,
        span_start=rates[0]["start"] if len(rates) > 0 else None,
        span_end=rates[-1]["end"] if len(rates) > 0 else None,
      )
      self._attributes["off_peak_windows"] = self._off_peak_windows_for_attribute(current)
      self._hass.async_create_task(self._async_save_history())

      self._last_updated = current

    self._attributes = dict_to_typed_dict(self._attributes)
    super()._handle_coordinator_update()

  def _off_peak_windows_for_attribute(self, current):
    """The recent slice of off-peak history to expose in the attribute (see OFF_PEAK_ATTRIBUTE_RETENTION_DAYS)."""
    attr_min_time = current - timedelta(days=OFF_PEAK_ATTRIBUTE_RETENTION_DAYS)
    return [w.to_dict() for w in self._off_peak_history if w.end >= attr_min_time]

  async def _async_save_history(self):
    await async_save_cached_off_peak_history(
      self._hass, self._mpan, self._serial_number, self._off_peak_history,
      dispatch_repair_done=self._dispatch_repair_done,
    )

  async def _async_repair_from_dispatches(self):
    """Put back what 21.0.0's clip took out of the stored history, once.

    That release rewrote the stored smart charging windows on every refresh and saved them,
    dropping and shortening any that overlapped. The windows themselves are gone from this
    store, but the started dispatches are kept separately for the same sixty days and were never
    touched, so the part of each lost window that actually ran can be added back. Nothing is
    taken away by this, and anything a dispatch did not run stays gone.

    Export meters have no smart charging windows to lose. Without a charger there is nothing to
    rebuild from, and nothing could have been lost either, so it simply looks again next time
    rather than recording that it is done - the devices may not have loaded yet.
    """
    if self._is_export or not self._intelligent_device_ids:
      return

    started = []
    loaded_any = False
    for device_id in self._intelligent_device_ids:
      dispatches = await async_load_cached_intelligent_dispatches(self._hass, self._account_id, device_id)
      if dispatches is not None:
        loaded_any = True
        started.extend(dispatches.started or [])

    if not loaded_any:
      return

    self._off_peak_history, added = rebuild_from_started_dispatches(
      self._off_peak_history, started, start_of_local_day()
    )
    self._dispatch_repair_done = True
    await self._async_save_history()

    if added > 0:
      _LOGGER.info(
        "Put back %d smart charging window(s) for %s/%s from the dispatches that ran",
        added, self._mpan, self._serial_number,
      )

  async def async_added_to_hass(self):
    """Call when entity about to be added to hass."""
    await super().async_added_to_hass()
    state = await self.async_get_last_state()

    if state is not None:
      self._state = None if state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN) or state.state is None else state.state.lower() == 'on'
      self._attributes = dict_to_typed_dict(state.attributes)

    if (self._state is None):
      self._state = False

    self._off_peak_history, self._dispatch_repair_done = await async_load_off_peak_history_store(
      self._hass, self._mpan, self._serial_number
    )
    if not self._dispatch_repair_done:
      await self._async_repair_from_dispatches()
    # Apply the same retention window as the coordinator update path, otherwise restoring the full
    # 60-day cached history would briefly blow past HA's attribute size limit on every restart.
    self._attributes["off_peak_windows"] = self._off_peak_windows_for_attribute(now())

    _LOGGER.debug(f'Restored EDFEnergyElectricityOffPeak state: {self._state}')
