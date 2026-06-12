import logging
from datetime import datetime

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN, EntityCategory
from homeassistant.components.sensor import RestoreSensor, SensorDeviceClass
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import generate_entity_id

from ..const import DATA_AUTH_TOKEN_EXPIRY, DOMAIN

_LOGGER = logging.getLogger(__name__)


def auth_expiry_dispatcher_signal(account_id: str) -> str:
  return f"edf_energy_auth_expiry_{account_id}"


class EDFEnergyAuthTokenExpiry(RestoreSensor):
  """Diagnostic sensor exposing when the EDF Energy refresh token expires."""

  def __init__(self, hass, account_id: str):
    self._account_id = account_id
    self._state = None
    self.entity_id = generate_entity_id("sensor.{}", self.unique_id, hass=hass)

  @property
  def unique_id(self):
    return f"edf_energy_{self._account_id}_auth_token_expiry"

  @property
  def name(self):
    return f"EDF Energy Auth Token Expiry ({self._account_id})"

  @property
  def device_class(self):
    return SensorDeviceClass.TIMESTAMP

  @property
  def entity_category(self):
    return EntityCategory.DIAGNOSTIC

  @property
  def entity_registry_enabled_default(self) -> bool:
    return True

  @property
  def native_value(self):
    return self._state

  async def async_added_to_hass(self):
    await super().async_added_to_hass()

    expiry = self.hass.data.get(DOMAIN, {}).get(self._account_id, {}).get(
      DATA_AUTH_TOKEN_EXPIRY.format(self._account_id)
    )
    if expiry is not None:
      self._state = expiry
    else:
      last_state = await self.async_get_last_state()
      if last_state and last_state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN):
        try:
          self._state = datetime.fromisoformat(last_state.state)
        except (ValueError, TypeError):
          pass

    self.async_on_remove(
      async_dispatcher_connect(
        self.hass,
        auth_expiry_dispatcher_signal(self._account_id),
        self._handle_expiry_update,
      )
    )

  @callback
  def _handle_expiry_update(self, expiry: datetime):
    self._state = expiry
    self.async_write_ha_state()
