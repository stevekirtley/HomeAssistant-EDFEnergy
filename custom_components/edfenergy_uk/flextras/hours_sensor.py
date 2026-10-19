"""The free hours a customer has left to spend, and when they expire.

The hours the sessions feed already publishes say when free electricity is coming. This
says what is still unspent, which is what an automation needs to act on - unused challenge
hours do not simply lapse, EDF books them for you at a time of their choosing, so the
useful trigger is an expiry approaching with hours still in hand.
"""
import logging
from datetime import datetime

from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import generate_entity_id
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util.dt import parse_datetime, utcnow

from ..coordinators.flextras_hours import FlextrasHoursCoordinatorResult
from ..utils.attributes import dict_to_typed_dict

_LOGGER = logging.getLogger(__name__)


def next_expiry(entitlements, current: datetime):
  """The soonest expiry that still has hours against it, and how far off it is.

  Buckets with nothing left are ignored - an expiry that cannot cost anything is not
  worth waking an automation for. A bucket whose remaining hours could not be read from
  EDF's prose counts as having hours, because treating an unknown as zero would hide a
  real expiry.
  """
  soonest, hours = None, None
  for item in entitlements or []:
    left = item.get("hours_left")
    if left == 0:
      continue
    expires = parse_datetime(item.get("expires") or "")
    if expires is None:
      continue
    if soonest is None or expires < soonest:
      soonest, hours = expires, left
  if soonest is None:
    return None, None, None
  return soonest, hours, max(0, (soonest - current).days)


class EDFEnergyFlextrasHoursRemaining(CoordinatorEntity, SensorEntity):
  """Free hours earned through Flextras that have not been booked yet."""

  def __init__(self, hass: HomeAssistant, coordinator, account_id: str):
    CoordinatorEntity.__init__(self, coordinator)
    self._account_id = account_id
    self._state = None
    self._attributes = {"account_id": account_id}
    self.entity_id = generate_entity_id("sensor.{}", self.unique_id, hass=hass)

  @property
  def unique_id(self):
    return f"edf_energy_{self._account_id}_flextras_hours_remaining"

  @property
  def name(self):
    return f"Flextras Hours Remaining ({self._account_id})"

  @property
  def icon(self):
    return "mdi:clock-plus-outline"

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
    await super().async_added_to_hass()
    self._handle_coordinator_update()

  @callback
  def _handle_coordinator_update(self) -> None:
    result: FlextrasHoursCoordinatorResult = self.coordinator.data if self.coordinator is not None else None
    if result is not None:
      self._state = result.total_remaining_hours
      expires_at, expiring_hours, days = next_expiry(result.entitlements, utcnow())
      self._attributes = dict_to_typed_dict({
        "account_id": self._account_id,
        "bonus_hours_remaining": result.bonus_hours_remaining,
        "challenge_hours_remaining": result.challenge_hours_remaining,
        "hours_booked": len(result.hours),
        "booked_hours": [f"{date} {time}" for date, time in result.hours],
        # Each bucket with its own expiry, which the totals above flatten away.
        "entitlements": result.entitlements,
        "next_expiry": expires_at,
        "hours_expiring_next": expiring_hours,
        "days_until_expiry": days,
        "bookable_days": [d["date"] for d in result.bookable_days if d.get("available")],
      })
      # Deliberately no "last retrieved" timestamp here. These attributes are a fair size,
      # and a value that moves on every refresh would write a recorder row every thirty
      # minutes whether anything changed or not. This integration keeps retrieval times in
      # their own diagnostic entities for exactly that reason.

    super()._handle_coordinator_update()
