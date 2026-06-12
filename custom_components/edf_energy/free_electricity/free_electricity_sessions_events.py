import logging

from homeassistant.core import HomeAssistant, callback

from homeassistant.components.event import (
    EventEntity,
    EventExtraStoredData,
)
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.entity import generate_entity_id

from ..const import EVENT_ALL_FREE_ELECTRICITY_SESSIONS

from ..utils.attributes import dict_to_typed_dict
from .base import EDFEnergyFreeElectricitySensor

_LOGGER = logging.getLogger(__name__)


class EDFEnergyFreeElectricitySessionEvents(EDFEnergyFreeElectricitySensor, EventEntity, RestoreEntity):
  """Sensor for displaying the upcoming free electricity sessions.

  Exposes every known free electricity session (from all sources) in an `events` attribute,
  matching the shape of the Octopus integration's free electricity session events sensor so
  that Predbat - and any other consumer expecting that format - can read it directly.
  """

  _attr_translation_key = "free_electricity_sessions"

  def __init__(self, hass: HomeAssistant, account_id: str):
    """Init sensor."""

    EDFEnergyFreeElectricitySensor.__init__(self, account_id)

    self._account_id = account_id
    self._hass = hass
    self._state = None
    self._last_updated = None

    self._attr_event_types = [EVENT_ALL_FREE_ELECTRICITY_SESSIONS]
    self.entity_id = generate_entity_id("event.{}", self.unique_id, hass=hass)

  @property
  def unique_id(self):
    """The id of the sensor."""
    return f"edf_energy_{self._account_id}_free_electricity_session_events"

  @property
  def name(self):
    """Name of the sensor."""
    return f"Free Electricity Session Events ({self._account_id})"

  async def async_added_to_hass(self):
    """Call when entity about to be added to hass."""
    # If not None, we got an initial value.
    await super().async_added_to_hass()

    self._hass.bus.async_listen(self._attr_event_types[0], self._async_handle_event)

  async def async_get_last_event_data(self):
    data = await super().async_get_last_event_data()
    return EventExtraStoredData.from_dict({
      "last_event_type": data.last_event_type,
      "last_event_attributes": dict_to_typed_dict(data.last_event_attributes),
    })

  @callback
  def _async_handle_event(self, event) -> None:
    if (event.data is not None and "account_id" in event.data and event.data["account_id"] == self._account_id):
      self._trigger_event(event.event_type, event.data)
      self.async_write_ha_state()
