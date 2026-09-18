"""Buttons for the Flextras actions the integration can perform.

Only actions captured from the EDF mobile app are exposed here. Joining the
Weekend Saver challenge is deliberately absent - that endpoint is not known, and
guessing it risks unintended account changes.

Leaving Flextras is not exposed as a button: it is reversible, but it resets the
registration date and is an unfortunate thing to press by accident on a
dashboard. It is available as the edf_energy.join_flextras action's counterpart
in the API client if ever needed.
"""
import logging

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import generate_entity_id
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.components.button import ButtonEntity

from ..coordinators.flextras import FlextrasCoordinatorResult, get_property_id

_LOGGER = logging.getLogger(__name__)


class EDFEnergyFlextrasRegisterPowerPerks(CoordinatorEntity, ButtonEntity):
  """Register the account for Power Perks (short-notice free electricity slots).

  Disabled once registered, and while the account is not on Flextras, since the
  endpoint requires Flextras membership.
  """

  def __init__(self, hass: HomeAssistant, coordinator, client, account_id: str):
    CoordinatorEntity.__init__(self, coordinator)
    self._hass = hass
    self._client = client
    self._account_id = account_id
    self._available = False
    self.entity_id = generate_entity_id("button.{}", self.unique_id, hass=hass)

  @property
  def unique_id(self):
    return f"edf_energy_{self._account_id}_flextras_register_power_perks"

  @property
  def name(self):
    return f"Flextras Register Power Perks ({self._account_id})"

  @property
  def icon(self):
    return "mdi:flash-alert-outline"

  @property
  def available(self):
    return self._available

  async def async_added_to_hass(self) -> None:
    await super().async_added_to_hass()
    self._handle_coordinator_update()

  @callback
  def _handle_coordinator_update(self) -> None:
    result: FlextrasCoordinatorResult = self.coordinator.data if self.coordinator is not None else None
    if result is not None:
      registered_for_flextras = bool(result.registered) and not bool(result.opted_out)
      self._available = registered_for_flextras and result.power_perks_signup_date is None
    super()._handle_coordinator_update()

  async def async_press(self) -> None:
    result = await self._client.async_register_power_perks(self._account_id)
    if result is None:
      _LOGGER.warning("Power Perks registration failed for %s", self._account_id)
    await self.coordinator.async_request_refresh()


class EDFEnergyFlextrasClaimBonusHours(CoordinatorEntity, ButtonEntity):
  """Claim the Flextras joining bonus hours.

  Disabled once claimed, or when the account has no property id to send.
  """

  def __init__(self, hass: HomeAssistant, coordinator, client, account_id: str):
    CoordinatorEntity.__init__(self, coordinator)
    self._hass = hass
    self._client = client
    self._account_id = account_id
    self._available = False
    self.entity_id = generate_entity_id("button.{}", self.unique_id, hass=hass)

  @property
  def unique_id(self):
    return f"edf_energy_{self._account_id}_flextras_claim_bonus_hours"

  @property
  def name(self):
    return f"Flextras Claim Bonus Hours ({self._account_id})"

  @property
  def icon(self):
    return "mdi:gift-open-outline"

  @property
  def available(self):
    return self._available

  async def async_added_to_hass(self) -> None:
    await super().async_added_to_hass()
    self._handle_coordinator_update()

  @callback
  def _handle_coordinator_update(self) -> None:
    result: FlextrasCoordinatorResult = self.coordinator.data if self.coordinator is not None else None
    if result is not None:
      self._available = (
        bool(result.registered)
        and not bool(result.opted_out)
        and result.bonus_hours_claimed is not True
      )
    super()._handle_coordinator_update()

  async def async_press(self) -> None:
    property_id = get_property_id(self._hass, self._account_id)
    if property_id is None:
      _LOGGER.warning(
        "Cannot claim Flextras bonus hours for %s: no property id available", self._account_id
      )
      return
    result = await self._client.async_claim_flextras_bonus_hours(self._account_id, property_id)
    if result is None:
      _LOGGER.warning("Flextras bonus hours claim failed for %s", self._account_id)
    await self.coordinator.async_request_refresh()


class EDFEnergyFlextrasJoin(CoordinatorEntity, ButtonEntity):
  """Join Flextras.

  Only available while the account is not a member, so it disappears from use
  once joined rather than offering a no-op.
  """

  def __init__(self, hass: HomeAssistant, coordinator, client, account_id: str):
    CoordinatorEntity.__init__(self, coordinator)
    self._hass = hass
    self._client = client
    self._account_id = account_id
    self._available = False
    self.entity_id = generate_entity_id("button.{}", self.unique_id, hass=hass)

  @property
  def unique_id(self):
    return f"edf_energy_{self._account_id}_flextras_join"

  @property
  def name(self):
    return f"Flextras Join ({self._account_id})"

  @property
  def icon(self):
    return "mdi:star-plus-outline"

  @property
  def available(self):
    return self._available

  async def async_added_to_hass(self) -> None:
    await super().async_added_to_hass()
    self._handle_coordinator_update()

  @callback
  def _handle_coordinator_update(self) -> None:
    result: FlextrasCoordinatorResult = self.coordinator.data if self.coordinator is not None else None
    if result is not None:
      # Never registered, or registered and since opted out.
      self._available = not bool(result.registered) or bool(result.opted_out)
    super()._handle_coordinator_update()

  async def async_press(self) -> None:
    result = await self._client.async_register_flextras(self._account_id)
    if result is None:
      _LOGGER.warning("Flextras join failed for %s", self._account_id)
    await self.coordinator.async_request_refresh()
