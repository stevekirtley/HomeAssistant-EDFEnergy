import logging

from homeassistant.core import HomeAssistant, callback
from homeassistant.components.event import EventEntity, EventExtraStoredData
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.entity import generate_entity_id

from ..const import EVENT_ALL_FREE_ELECTRICITY_SESSIONS
from ..utils.attributes import dict_to_typed_dict
from .base import EDFEnergyFreeElectricitySensor

_LOGGER = logging.getLogger(__name__)


class EDFEnergyFreeElectricitySessionEvents(EDFEnergyFreeElectricitySensor, EventEntity, RestoreEntity):
  """Exposes all free electricity sessions in an Octopus-compatible events attribute.

  The `events` attribute carries `{code, source, start, end, duration_in_minutes}` entries,
  matching the shape of octopus_energy's free electricity session events sensor so that
  Predbat and other consumers work without special-casing.
  """

  _attr_translation_key = "free_electricity_sessions"

  def __init__(self, hass: HomeAssistant, account_id: str):
    EDFEnergyFreeElectricitySensor.__init__(self, account_id)
    self._account_id = account_id
    self._hass = hass
    self._football_enabled = False
    self._attr_event_types = [EVENT_ALL_FREE_ELECTRICITY_SESSIONS]
    self.entity_id = generate_entity_id("event.{}", self.unique_id, hass=hass)

  @property
  def unique_id(self):
    return f"edf_energy_{self._account_id}_free_electricity_session_events"

  @property
  def name(self):
    return f"Free Electricity Session Events ({self._account_id})"

  @property
  def extra_state_attributes(self):
    return {
      "football_free_electricity_enabled": self._football_enabled,
    }

  def update_football_enabled(self, enabled: bool):
    """Called by the coordinator after a service toggle so the attribute stays current."""
    self._football_enabled = enabled

  async def async_added_to_hass(self):
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
    if event.data is not None and event.data.get("account_id") == self._account_id:
      football_enabled = event.data.get("football_free_electricity_enabled", False)
      self._football_enabled = football_enabled
      self._trigger_event(event.event_type, event.data)
      self.async_write_ha_state()
