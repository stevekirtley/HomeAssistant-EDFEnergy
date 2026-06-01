import logging

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import generate_entity_id
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.components.sensor import (
  RestoreSensor,
  SensorDeviceClass,
)
from homeassistant.util.dt import now as ha_now

from ..coordinators.sunday_saver import SundaySaverCoordinatorResult
from ..storage.sunday_saver_history import (
  SundaySaverWindowRecord,
  merge_sunday_saver_windows,
  async_load_cached_sunday_saver_history,
  async_save_cached_sunday_saver_history,
)
from ..utils.attributes import dict_to_typed_dict

_LOGGER = logging.getLogger(__name__)


class EDFEnergySundaySaverStartSensor(CoordinatorEntity, RestoreSensor):
  """Sensor for the next Sunday Saver free energy window start time.

  Also owns the 60-day rolling history exposed as 'sunday_saver_windows'
  which the EDF Energy panel reads to render the Sunday Saver section.
  """

  def __init__(self, hass: HomeAssistant, coordinator, account_id: str):
    CoordinatorEntity.__init__(self, coordinator)
    self._account_id = account_id
    self._state = None
    self._history: list[SundaySaverWindowRecord] = []
    self._attributes = {
      "account_id": account_id,
      "has_event": None,
      "free_hours": None,
      "end": None,
      "is_active": None,
      "sunday_saver_windows": [],
    }
    self.entity_id = generate_entity_id("sensor.{}", self.unique_id, hass=hass)

  @property
  def unique_id(self):
    return f"edf_energy_{self._account_id}_sunday_saver_start"

  @property
  def name(self):
    return f"Sunday Saver Start ({self._account_id})"

  @property
  def device_class(self):
    return SensorDeviceClass.TIMESTAMP

  @property
  def icon(self):
    return "mdi:lightning-bolt-circle"

  @property
  def extra_state_attributes(self):
    return self._attributes

  @property
  def native_value(self):
    return self._state

  @callback
  def _handle_coordinator_update(self) -> None:
    current = ha_now()
    result: SundaySaverCoordinatorResult = (
      self.coordinator.data
      if self.coordinator is not None and self.coordinator.data is not None
      else None
    )

    if result is not None:
      _LOGGER.debug(f"Updating EDFEnergySundaySaverStartSensor for account '{self._account_id}'")

      if result.has_event and result.start is not None:
        self._state = result.start
        is_active = (
          result.start <= current <= result.end
          if result.end is not None
          else False
        )
        new_window = SundaySaverWindowRecord(result.start, result.end, result.free_hours)
        self._history = merge_sunday_saver_windows(self._history, [new_window], current)
        self.hass.async_create_task(self._async_save_history())
      else:
        self._state = None
        is_active = False

      self._attributes = dict_to_typed_dict({
        "account_id": self._account_id,
        "has_event": result.has_event,
        "free_hours": result.free_hours if result.has_event else None,
        "end": result.end,
        "is_active": is_active,
        "sunday_saver_windows": [w.to_dict() for w in self._history],
      })

    super()._handle_coordinator_update()

  async def _async_save_history(self):
    await async_save_cached_sunday_saver_history(self.hass, self._account_id, self._history)

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
      _LOGGER.debug(f'Restored EDFEnergySundaySaverStartSensor state: {self._state}')

    self._history = await async_load_cached_sunday_saver_history(self.hass, self._account_id)
    self._attributes["sunday_saver_windows"] = [w.to_dict() for w in self._history]


class EDFEnergySundaySaverEndSensor(CoordinatorEntity, RestoreSensor):
  """Sensor for the next Sunday Saver free energy window end time."""

  def __init__(self, hass: HomeAssistant, coordinator, account_id: str):
    CoordinatorEntity.__init__(self, coordinator)
    self._account_id = account_id
    self._state = None
    self._attributes = {
      "account_id": account_id,
      "has_event": None,
      "free_hours": None,
      "start": None,
      "is_active": None,
    }
    self.entity_id = generate_entity_id("sensor.{}", self.unique_id, hass=hass)

  @property
  def unique_id(self):
    return f"edf_energy_{self._account_id}_sunday_saver_end"

  @property
  def name(self):
    return f"Sunday Saver End ({self._account_id})"

  @property
  def device_class(self):
    return SensorDeviceClass.TIMESTAMP

  @property
  def icon(self):
    return "mdi:lightning-bolt-circle"

  @property
  def extra_state_attributes(self):
    return self._attributes

  @property
  def native_value(self):
    return self._state

  @callback
  def _handle_coordinator_update(self) -> None:
    current = ha_now()
    result: SundaySaverCoordinatorResult = (
      self.coordinator.data
      if self.coordinator is not None and self.coordinator.data is not None
      else None
    )

    if result is not None:
      _LOGGER.debug(f"Updating EDFEnergySundaySaverEndSensor for account '{self._account_id}'")

      if result.has_event and result.end is not None:
        self._state = result.end
        is_active = (
          result.start <= current <= result.end
          if result.start is not None
          else False
        )
      else:
        self._state = None
        is_active = False

      self._attributes = dict_to_typed_dict({
        "account_id": self._account_id,
        "has_event": result.has_event,
        "free_hours": result.free_hours if result.has_event else None,
        "start": result.start,
        "is_active": is_active,
      })

    super()._handle_coordinator_update()

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
      _LOGGER.debug(f'Restored EDFEnergySundaySaverEndSensor state: {self._state}')
