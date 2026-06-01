from datetime import timedelta
import logging

from homeassistant.const import (
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import generate_entity_id

from homeassistant.util.dt import (now)
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
  async_load_cached_off_peak_history,
  async_save_cached_off_peak_history,
)

from .base import EDFEnergyElectricitySensor
from ..utils.attributes import dict_to_typed_dict

_LOGGER = logging.getLogger(__name__)

class EDFEnergyElectricityOffPeak(CoordinatorEntity, EDFEnergyElectricitySensor, BinarySensorEntity, RestoreEntity):
  """Sensor for determining if the current rate is off peak."""

  def __init__(self, hass: HomeAssistant, coordinator, meter, point):
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

      # Accumulate off-peak windows from the current rates data
      new_windows = [
        OffPeakWindowRecord(w["start"], w["end"], w["is_intelligent_adjusted"])
        for w in get_off_peak_windows_from_rates(rates)
      ]
      self._off_peak_history = merge_off_peak_windows(self._off_peak_history, new_windows, current)
      attr_min_time = current - timedelta(days=7)
      self._attributes["off_peak_windows"] = [w.to_dict() for w in self._off_peak_history if w.end >= attr_min_time]
      self._hass.async_create_task(self._async_save_history())

      self._last_updated = current

    self._attributes = dict_to_typed_dict(self._attributes)
    super()._handle_coordinator_update()

  async def _async_save_history(self):
    await async_save_cached_off_peak_history(
      self._hass, self._mpan, self._serial_number, self._off_peak_history
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

    self._off_peak_history = await async_load_cached_off_peak_history(
      self._hass, self._mpan, self._serial_number
    )
    self._attributes["off_peak_windows"] = [w.to_dict() for w in self._off_peak_history]

    _LOGGER.debug(f'Restored EDFEnergyElectricityOffPeak state: {self._state}')
