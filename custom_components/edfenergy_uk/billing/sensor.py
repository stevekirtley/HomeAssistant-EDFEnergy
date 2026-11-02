"""Sensors for the account's billing position.

Four of them, all fed by the one billing coordinator: the balance, the last statement, the
next payment and where any refund request has got to. Between them they cover what people
build notifications and dashboard cards around.

What is deliberately *not* here: the statement list, the ledger and the referral list. Each
is dozens or hundreds of rows, several carry other people's names, and none of it is
something an automation can usefully trigger on. Putting them in attributes would write
all of it into the recorder database every time it changed, so the panel asks for them
over the websocket when the tab is open and nothing is persisted.
"""
import logging
from datetime import date, timedelta

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import generate_entity_id
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass

from ..coordinators.billing import BillingCoordinatorResult
from ..utils.attributes import dict_to_typed_dict

_LOGGER = logging.getLogger(__name__)


def next_payment_date(schedule: dict | None, today: date) -> date | None:
  """When the next collection is due, from the day of the month EDF hold.

  Only the day is given, not a date, so the next occurrence is worked out here: this month
  if it has not passed, otherwise next. A day beyond the length of the month lands on the
  last day of it, which is what EDF do with a 31st on a short month.
  """
  if not schedule:
    return None

  day = schedule.get("day")
  if day is None:
    return None

  try:
    day = int(day)
  except (TypeError, ValueError):
    return None

  if day < 1:
    return None

  def _clamped(year: int, month: int) -> date:
    # The first of the month after, less a day, is the last day of this one - no calendar
    # table and no leap year special case.
    first_of_next = date(year + (1 if month == 12 else 0), 1 if month == 12 else month + 1, 1)
    last_day = (first_of_next - timedelta(days=1)).day
    return date(year, month, min(day, last_day))

  this_month = _clamped(today.year, today.month)
  if this_month >= today:
    return this_month
  return _clamped(today.year + (1 if today.month == 12 else 0), 1 if today.month == 12 else today.month + 1)


class EDFEnergyBillingSensor(CoordinatorEntity, SensorEntity):
  """Shared plumbing for the billing sensors: all four read one coordinator result."""

  def __init__(self, hass: HomeAssistant, coordinator, account_id: str):
    CoordinatorEntity.__init__(self, coordinator)
    self._account_id = account_id
    self._state = None
    self._attributes = {"account_id": account_id}
    self.entity_id = generate_entity_id("sensor.{}", self.unique_id, hass=hass)

  @property
  def native_value(self):
    return self._state

  @property
  def extra_state_attributes(self):
    return self._attributes

  async def async_added_to_hass(self) -> None:
    """Populate from what the coordinator already holds rather than waiting a tick."""
    await super().async_added_to_hass()
    self._handle_coordinator_update()

  @callback
  def _handle_coordinator_update(self) -> None:
    result: BillingCoordinatorResult = self.coordinator.data if self.coordinator is not None else None
    summary = result.summary if result is not None else None
    if summary is not None:
      self._update_from_summary(summary)

    super()._handle_coordinator_update()

  def _update_from_summary(self, summary: dict) -> None:
    raise NotImplementedError


class EDFEnergyAccountBalance(EDFEnergyBillingSensor):
  """What the account is in credit by, as EDF report it.

  Positive is credit, which is the usual state for a direct debit account, and it is passed
  through with EDF's own sign rather than flipped so it reads the same as the app and the
  bill. Note that this is not what is refundable - see the refund status sensor.
  """

  @property
  def unique_id(self):
    return f"edf_energy_{self._account_id}_account_balance"

  @property
  def name(self):
    return f"Account Balance ({self._account_id})"

  @property
  def icon(self):
    return "mdi:scale-balance"

  @property
  def device_class(self):
    return SensorDeviceClass.MONETARY

  @property
  def state_class(self):
    return SensorStateClass.TOTAL

  @property
  def native_unit_of_measurement(self):
    return "GBP"

  def _update_from_summary(self, summary: dict) -> None:
    self._state = summary.get("balance")
    self._attributes = dict_to_typed_dict({
      "account_id": self._account_id,
      "account_status": summary.get("status"),
    })


class EDFEnergyLastBillAmount(EDFEnergyBillingSensor):
  """The charges on the most recent statement, with its dates as attributes."""

  @property
  def unique_id(self):
    return f"edf_energy_{self._account_id}_last_bill_amount"

  @property
  def name(self):
    return f"Last Bill Amount ({self._account_id})"

  @property
  def icon(self):
    return "mdi:file-document-outline"

  @property
  def device_class(self):
    return SensorDeviceClass.MONETARY

  @property
  def state_class(self):
    return SensorStateClass.TOTAL

  @property
  def native_unit_of_measurement(self):
    return "GBP"

  def _update_from_summary(self, summary: dict) -> None:
    bill = summary.get("last_bill") or {}
    self._state = bill.get("amount")
    self._attributes = dict_to_typed_dict({
      "account_id": self._account_id,
      "bill_id": bill.get("id"),
      "issued_date": bill.get("issued_date"),
      "period_from": bill.get("from_date"),
      "period_to": bill.get("to_date"),
      "due_date": bill.get("due_date"),
      "closing_balance": bill.get("closing_balance"),
    })


class EDFEnergyNextPaymentAmount(EDFEnergyBillingSensor):
  """The next direct debit collection, with the date it is due as an attribute.

  A variable schedule - EDF collecting whatever the period came to rather than a fixed
  amount - has no figure to report until the statement is cut, so the state is unknown and
  `is_variable` says why.
  """

  @property
  def unique_id(self):
    return f"edf_energy_{self._account_id}_next_payment_amount"

  @property
  def name(self):
    return f"Next Payment Amount ({self._account_id})"

  @property
  def icon(self):
    return "mdi:cash-clock"

  @property
  def device_class(self):
    return SensorDeviceClass.MONETARY

  @property
  def state_class(self):
    return SensorStateClass.TOTAL

  @property
  def native_unit_of_measurement(self):
    return "GBP"

  def _update_from_summary(self, summary: dict) -> None:
    schedule = summary.get("payment_schedule") or {}
    is_variable = schedule.get("is_variable") == True
    amount = schedule.get("amount")

    self._state = None if is_variable or not amount else amount

    due = next_payment_date(schedule, date.today())
    self._attributes = dict_to_typed_dict({
      "account_id": self._account_id,
      "next_payment_date": due.isoformat() if due is not None else None,
      "payment_day": schedule.get("day"),
      "frequency": schedule.get("frequency"),
      "is_variable": is_variable,
      "payment_method": schedule.get("type"),
    })


# A request that has not been answered yet. Anything else - PAID, CANCELLED, REJECTED - is
# finished with, so the sensor stops counting it as outstanding.
OPEN_REPAYMENT_STATUSES = ("REQUESTED", "SUBMITTED", "APPROVED", "PENDING")


class EDFEnergyRefundStatus(EDFEnergyBillingSensor):
  """Where the most recent refund request has got to, and whether another can be made.

  The state is the latest request's status, or 'None requested' on an account that has
  never asked for one. `maximum_refund` is what EDF would actually allow: it tracks what
  has been paid in by direct debit and is normally far below the balance, so it is the
  figure to act on rather than the credit on the account.
  """

  @property
  def unique_id(self):
    return f"edf_energy_{self._account_id}_refund_status"

  @property
  def name(self):
    return f"Refund Status ({self._account_id})"

  @property
  def icon(self):
    return "mdi:cash-refund"

  def _update_from_summary(self, summary: dict) -> None:
    refund = summary.get("refund") or {}
    requests = refund.get("requests") or []
    latest = requests[0] if requests else None

    self._state = latest.get("status") if latest is not None else "None requested"

    open_requests = [r for r in requests if (r.get("status") or "").upper() in OPEN_REPAYMENT_STATUSES]

    self._attributes = dict_to_typed_dict({
      "account_id": self._account_id,
      "amount": latest.get("amount") if latest is not None else None,
      "payment_date": latest.get("payment_date") if latest is not None else None,
      "reason": latest.get("reason") if latest is not None else None,
      "open_requests": len(open_requests),
      "can_request_refund": refund.get("can_request"),
      # EDF's own code when they will not allow one, e.g. HAS_NOT_GIVEN_READINGS_RECENTLY.
      "cannot_request_reason": refund.get("reason"),
      "maximum_refund": refund.get("maximum"),
    })
