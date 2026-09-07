"""Sensors for EDF's Flextras scheme."""
import logging

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import generate_entity_id
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.const import UnitOfTime

from ..coordinators.flextras import FlextrasCoordinatorResult
from ..utils.attributes import dict_to_typed_dict

_LOGGER = logging.getLogger(__name__)


class EDFEnergyFlextrasBonusHours(CoordinatorEntity, SensorEntity):
  """Free electricity hours awarded by Flextras as a joining bonus.

  'claimed' distinguishes hours that have been accepted in the app from hours
  merely offered; unclaimed hours are not yet banked.
  """

  def __init__(self, hass: HomeAssistant, coordinator, account_id: str):
    CoordinatorEntity.__init__(self, coordinator)
    self._account_id = account_id
    self._state = None
    self._attributes = {"account_id": account_id}
    self.entity_id = generate_entity_id("sensor.{}", self.unique_id, hass=hass)

  @property
  def unique_id(self):
    return f"edf_energy_{self._account_id}_flextras_bonus_hours"

  @property
  def name(self):
    return f"Flextras Bonus Hours ({self._account_id})"

  @property
  def icon(self):
    return "mdi:gift-outline"

  @property
  def state_class(self):
    return SensorStateClass.MEASUREMENT

  @property
  def native_unit_of_measurement(self):
    return UnitOfTime.HOURS

  @property
  def native_value(self):
    return self._state

  @property
  def extra_state_attributes(self):
    return self._attributes

  async def async_added_to_hass(self) -> None:
    """Populate from the coordinator's existing data rather than waiting a tick."""
    await super().async_added_to_hass()
    self._handle_coordinator_update()

  @callback
  def _handle_coordinator_update(self) -> None:
    result: FlextrasCoordinatorResult = self.coordinator.data if self.coordinator is not None else None
    if result is not None:
      self._state = result.bonus_hours_awarded
      self._attributes = dict_to_typed_dict({
        "account_id": self._account_id,
        "claimed": result.bonus_hours_claimed,
        "registration_date": result.registration_date,
      })

    super()._handle_coordinator_update()
