"""Binary sensors for EDF's Flextras scheme and its sub-schemes."""
import logging

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import generate_entity_id
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.components.binary_sensor import BinarySensorEntity

from ..coordinators.flextras import FlextrasCoordinatorResult
from ..utils.attributes import dict_to_typed_dict

_LOGGER = logging.getLogger(__name__)


class EDFEnergyFlextrasRegistered(CoordinatorEntity, BinarySensorEntity):
  """Whether the account is currently signed up to Flextras.

  Registration can only be done in the EDF mobile app, so this is read-only.
  """

  def __init__(self, hass: HomeAssistant, coordinator, account_id: str):
    CoordinatorEntity.__init__(self, coordinator)
    self._account_id = account_id
    self._state = None
    self._attributes = {"account_id": account_id}
    self.entity_id = generate_entity_id("binary_sensor.{}", self.unique_id, hass=hass)

  @property
  def unique_id(self):
    return f"edf_energy_{self._account_id}_flextras_registered"

  @property
  def name(self):
    return f"Flextras Registered ({self._account_id})"

  @property
  def icon(self):
    return "mdi:star-circle-outline"

  @property
  def is_on(self):
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
      # Opting out leaves registrationDate populated, so both must be considered.
      self._state = bool(result.registered) and not bool(result.opted_out)
      self._attributes = {
        "account_id": self._account_id,
        "registration_date": result.registration_date,
        "opted_out": result.opted_out,
        "tastecard_activation_date": result.tastecard_date,
        "bonus_hours_awarded": result.bonus_hours_awarded,
        "bonus_hours_claimed": result.bonus_hours_claimed,
        "power_perks_signup_date": result.power_perks_signup_date,
        "weekend_saver_can_sign_up": result.weekend_saver_can_sign_up,
        "weekend_saver_blockers": result.weekend_saver_blockers,
        "weekend_saver_tariff_excluded": result.weekend_saver_tariff_excluded,
        "power_perks_excluded": result.power_perks_excluded,
        "eligibility": result.eligibility,
      }
      self._attributes = dict_to_typed_dict(self._attributes)

    super()._handle_coordinator_update()


class EDFEnergyFlextrasWeekendSaverEligible(CoordinatorEntity, BinarySensorEntity):
  """Whether the account can join the recurring Weekend Saver challenge.

  When off, 'blockers' carries EDF's own explanation (e.g. a tariff with three
  or more rates), which is more useful than the bare boolean.
  """

  def __init__(self, hass: HomeAssistant, coordinator, account_id: str):
    CoordinatorEntity.__init__(self, coordinator)
    self._account_id = account_id
    self._state = None
    self._attributes = {"account_id": account_id}
    self.entity_id = generate_entity_id("binary_sensor.{}", self.unique_id, hass=hass)

  @property
  def unique_id(self):
    return f"edf_energy_{self._account_id}_flextras_weekend_saver_eligible"

  @property
  def name(self):
    return f"Flextras Weekend Saver Eligible ({self._account_id})"

  @property
  def icon(self):
    return "mdi:calendar-weekend"

  @property
  def is_on(self):
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
      self._state = result.weekend_saver_can_sign_up
      self._attributes = dict_to_typed_dict({
        "account_id": self._account_id,
        "blockers": result.weekend_saver_blockers,
        "eligibility": result.eligibility,
      })

    super()._handle_coordinator_update()


class EDFEnergyFlextrasPowerPerksRegistered(CoordinatorEntity, BinarySensorEntity):
  """Whether the account is signed up to Power Perks.

  powerPerksSignUpDate is populated the moment the account registers, so a null
  here reliably means the account has not joined.
  """

  def __init__(self, hass: HomeAssistant, coordinator, account_id: str):
    CoordinatorEntity.__init__(self, coordinator)
    self._account_id = account_id
    self._state = None
    self._attributes = {"account_id": account_id}
    self.entity_id = generate_entity_id("binary_sensor.{}", self.unique_id, hass=hass)

  @property
  def unique_id(self):
    return f"edf_energy_{self._account_id}_flextras_power_perks_registered"

  @property
  def name(self):
    return f"Flextras Power Perks Registered ({self._account_id})"

  @property
  def icon(self):
    return "mdi:flash-outline"

  @property
  def is_on(self):
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
      self._state = result.power_perks_signup_date is not None
      self._attributes = dict_to_typed_dict({
        "account_id": self._account_id,
        "signup_date": result.power_perks_signup_date,
      })

    super()._handle_coordinator_update()
