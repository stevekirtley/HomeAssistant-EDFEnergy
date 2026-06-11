import logging

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import generate_entity_id
from homeassistant.components.sensor import RestoreSensor, SensorDeviceClass

from ..utils.attributes import dict_to_typed_dict

_LOGGER = logging.getLogger(__name__)


class EDFEnergyEventFreeStartSensor(RestoreSensor):
  """Sensor for the start of an event-based free electricity window.

  Populated by an external coordinator (e.g. World Cup match schedule).
  Returns None until a coordinator provides data.
  """

  def __init__(self, hass: HomeAssistant, account_id: str):
    super().__init__()
    self._account_id = account_id
    self._state = None
    self._attributes = {
      "account_id": account_id,
      "event_name": None,
      "end": None,
      "is_active": False,
    }
    self.entity_id = generate_entity_id("sensor.{}", self.unique_id, hass=hass)

  @property
  def unique_id(self):
    return f"edf_energy_{self._account_id}_event_free_start"

  @property
  def name(self):
    return f"Event Free Electricity Start ({self._account_id})"

  @property
  def device_class(self):
    return SensorDeviceClass.TIMESTAMP

  @property
  def icon(self):
    return "mdi:calendar-star"

  @property
  def extra_state_attributes(self):
    return self._attributes

  @property
  def native_value(self):
    return self._state

  async def async_added_to_hass(self):
    await super().async_added_to_hass()
    state = await self.async_get_last_state()
    last_sensor_state = await self.async_get_last_sensor_data()

    if state is not None and last_sensor_state is not None and self._state is None:
      self._state = (
        None
        if state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN)
        else last_sensor_state.native_value
      )
      self._attributes = dict_to_typed_dict(state.attributes)
      _LOGGER.debug(f"Restored EDFEnergyEventFreeStartSensor state: {self._state}")


class EDFEnergyEventFreeEndSensor(RestoreSensor):
  """Sensor for the end of an event-based free electricity window.

  Populated by an external coordinator (e.g. World Cup match schedule).
  Returns None until a coordinator provides data.
  """

  def __init__(self, hass: HomeAssistant, account_id: str):
    super().__init__()
    self._account_id = account_id
    self._state = None
    self._attributes = {
      "account_id": account_id,
      "event_name": None,
      "start": None,
      "is_active": False,
    }
    self.entity_id = generate_entity_id("sensor.{}", self.unique_id, hass=hass)

  @property
  def unique_id(self):
    return f"edf_energy_{self._account_id}_event_free_end"

  @property
  def name(self):
    return f"Event Free Electricity End ({self._account_id})"

  @property
  def device_class(self):
    return SensorDeviceClass.TIMESTAMP

  @property
  def icon(self):
    return "mdi:calendar-star"

  @property
  def extra_state_attributes(self):
    return self._attributes

  @property
  def native_value(self):
    return self._state

  async def async_added_to_hass(self):
    await super().async_added_to_hass()
    state = await self.async_get_last_state()
    last_sensor_state = await self.async_get_last_sensor_data()

    if state is not None and last_sensor_state is not None and self._state is None:
      self._state = (
        None
        if state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN)
        else last_sensor_state.native_value
      )
      self._attributes = dict_to_typed_dict(state.attributes)
      _LOGGER.debug(f"Restored EDFEnergyEventFreeEndSensor state: {self._state}")
