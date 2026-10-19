"""Start and end of the current or next free electricity session, whatever its source.

The Sunday Saver and World Cup sensors only ever knew about their own scheme, so an
automation had to pick one and fall back to the other. These read the merged sessions feed
instead - Sunday Saver, Power Perks, a football window, or whatever comes next - so one
pair of timestamps answers "when is the next free window?" regardless of who is running it.
"""
import logging

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import generate_entity_id
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.util.dt import now as ha_now

from . import current_or_next_free_electricity_session_event
from .base import EDFEnergyFreeElectricitySensor
from ..coordinators.free_electricity_sessions import FreeElectricitySessionsCoordinatorResult
from ..utils.attributes import dict_to_typed_dict

_LOGGER = logging.getLogger(__name__)


class _EDFEnergyNextFreeElectricitySessionSensor(CoordinatorEntity, EDFEnergyFreeElectricitySensor, SensorEntity):
  """Shared behaviour: track the current-or-next session and expose it as a timestamp."""

  _attr_should_poll = False
  _attr_device_class = SensorDeviceClass.TIMESTAMP
  _attr_icon = "mdi:lightning-bolt-circle"

  def __init__(self, hass: HomeAssistant, coordinator, account_id: str):
    CoordinatorEntity.__init__(self, coordinator)
    EDFEnergyFreeElectricitySensor.__init__(self, account_id)
    self._account_id = account_id
    self._state = None
    self._attributes = self._empty_attributes()
    self.entity_id = generate_entity_id("sensor.{}", self.unique_id, hass=hass)

  def _empty_attributes(self) -> dict:
    return {
      "account_id": self._account_id,
      "code": None,
      "source": None,
      "start": None,
      "end": None,
      "duration_in_minutes": None,
      "is_active": False,
    }

  @property
  def extra_state_attributes(self):
    return self._attributes

  @property
  def native_value(self):
    return self._state

  def _pick(self, session):
    """Which timestamp this sensor reports - overridden per sensor."""
    raise NotImplementedError

  @callback
  def _handle_coordinator_update(self) -> None:
    current = ha_now()
    result: FreeElectricitySessionsCoordinatorResult = (
      self.coordinator.data if self.coordinator is not None else None
    )
    session = current_or_next_free_electricity_session_event(current, result.events) if result is not None else None

    if session is None:
      self._state = None
      self._attributes = self._empty_attributes()
    else:
      self._state = self._pick(session)
      self._attributes = dict_to_typed_dict({
        "account_id": self._account_id,
        "code": session.code,
        "source": session.source,
        "start": session.start,
        "end": session.end,
        "duration_in_minutes": session.duration_in_minutes,
        "is_active": session.start <= current <= session.end,
      })

    super()._handle_coordinator_update()

  async def async_added_to_hass(self):
    await super().async_added_to_hass()
    self._handle_coordinator_update()


class EDFEnergyNextFreeElectricitySessionStartSensor(_EDFEnergyNextFreeElectricitySessionSensor):
  """When the current or next free electricity session starts, from any source."""

  @property
  def unique_id(self):
    return f"edf_energy_{self._account_id}_next_free_electricity_session_start"

  @property
  def name(self):
    return f"Next Free Electricity Session Start ({self._account_id})"

  def _pick(self, session):
    return session.start


class EDFEnergyNextFreeElectricitySessionEndSensor(_EDFEnergyNextFreeElectricitySessionSensor):
  """When the current or next free electricity session ends, from any source."""

  @property
  def unique_id(self):
    return f"edf_energy_{self._account_id}_next_free_electricity_session_end"

  @property
  def name(self):
    return f"Next Free Electricity Session End ({self._account_id})"

  def _pick(self, session):
    return session.end
