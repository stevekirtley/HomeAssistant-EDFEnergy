"""The four billing sensors, and the next-payment date they have to work out themselves."""
from datetime import date

import pytest

from custom_components.edf_energy.billing.sensor import (
  EDFEnergyAccountBalance,
  EDFEnergyLastBillAmount,
  EDFEnergyNextPaymentAmount,
  EDFEnergyRefundStatus,
  next_payment_date,
)

ACCOUNT_ID = "A-1A2B3C4D"

SUMMARY = {
  "balance": 1234.56,
  "status": "ACTIVE",
  "last_bill": {"id": "117961351", "bill_type": "STATEMENT", "from_date": "2026-09-14",
                "to_date": "2026-10-06", "issued_date": "2026-10-07", "due_date": "2026-10-22",
                "closing_balance": 5264.46, "amount": 57.95},
  "payment_schedule": {"amount": 125.0, "day": 1, "frequency": "Monthly", "is_variable": False,
                       "type": "DIRECT_DEBIT", "valid_from": "2026-07-09", "valid_to": None},
  "refund": {"can_request": False, "reason": "HAS_NOT_GIVEN_READINGS_RECENTLY", "maximum": 98.76,
             "requests": [
               {"id": "2443432", "amount": 250.0, "payment_date": "2026-10-14", "status": "SUBMITTED",
                "reason": "PARTIAL_CREDIT_REFUND"},
               {"id": "2403503", "amount": 250.0, "payment_date": "2026-09-28", "status": "PAID",
                "reason": "PARTIAL_CREDIT_REFUND"},
             ]},
}

class StubResult:
  def __init__(self, summary):
    self.summary = summary

class StubCoordinator:
  def __init__(self, summary):
    self.data = StubResult(summary)

def build(cls, summary=SUMMARY):
  """Build a sensor without going anywhere near hass's entity id generation."""
  sensor = cls.__new__(cls)
  sensor.coordinator = StubCoordinator(summary)
  sensor._account_id = ACCOUNT_ID
  sensor._state = None
  sensor._attributes = {}
  sensor._update_from_summary(summary)
  return sensor

# ── Balance ───────────────────────────────────────────────────────────────────

def test_the_balance_is_reported_with_edfs_own_sign():
  # A credit balance is positive, as it is on the bill and in the app. Flipping it would
  # read as debt.
  # Act
  sensor = build(EDFEnergyAccountBalance)

  # Assert
  assert sensor.native_value == 1234.56
  assert sensor.extra_state_attributes["account_status"] == "ACTIVE"

# ── Last bill ─────────────────────────────────────────────────────────────────

def test_the_last_bill_sensor_is_the_charges_not_the_balance():
  # Act
  sensor = build(EDFEnergyLastBillAmount)

  # Assert
  assert sensor.native_value == 57.95
  # The attribute helper turns date strings into datetimes, which is what HA wants on an
  # attribute, so the date is compared rather than the text.
  assert sensor.extra_state_attributes["issued_date"].date().isoformat() == "2026-10-07"
  assert sensor.extra_state_attributes["closing_balance"] == 5264.46

def test_an_account_with_no_statements_yet_reports_nothing_rather_than_zero():
  # Act
  sensor = build(EDFEnergyLastBillAmount, {**SUMMARY, "last_bill": None})

  # Assert
  assert sensor.native_value is None

# ── Next payment ──────────────────────────────────────────────────────────────

def test_the_next_payment_carries_its_amount_and_date():
  # Act
  sensor = build(EDFEnergyNextPaymentAmount)

  # Assert
  assert sensor.native_value == 125.0
  assert sensor.extra_state_attributes["payment_day"] == 1
  assert sensor.extra_state_attributes["next_payment_date"] is not None

def test_a_variable_schedule_reports_no_amount_and_says_why():
  # EDF collect whatever the period came to, and paymentAmount is 0, which would read as a
  # free month.
  # Arrange
  summary = {**SUMMARY, "payment_schedule": {**SUMMARY["payment_schedule"],
                                             "is_variable": True, "amount": 0}}

  # Act
  sensor = build(EDFEnergyNextPaymentAmount, summary)

  # Assert
  assert sensor.native_value is None
  assert sensor.extra_state_attributes["is_variable"] == True

# ── Working out the payment date ──────────────────────────────────────────────

def test_a_payment_day_still_to_come_is_this_month():
  assert next_payment_date({"day": 20}, date(2026, 10, 15)) == date(2026, 10, 20)

def test_a_payment_day_already_past_is_next_month():
  assert next_payment_date({"day": 1}, date(2026, 10, 15)) == date(2026, 11, 1)

def test_todays_payment_day_is_today():
  assert next_payment_date({"day": 15}, date(2026, 10, 15)) == date(2026, 10, 15)

def test_december_rolls_into_january():
  assert next_payment_date({"day": 1}, date(2026, 12, 15)) == date(2027, 1, 1)

def test_the_31st_lands_on_the_last_day_of_a_short_month():
  # Which is what EDF do with it, rather than skipping the month.
  assert next_payment_date({"day": 31}, date(2026, 11, 1)) == date(2026, 11, 30)
  assert next_payment_date({"day": 31}, date(2027, 2, 1)) == date(2027, 2, 28)

def test_a_leap_february_is_handled():
  assert next_payment_date({"day": 31}, date(2028, 2, 1)) == date(2028, 2, 29)

def test_no_schedule_means_no_date_rather_than_a_guess():
  assert next_payment_date(None, date(2026, 10, 15)) is None
  assert next_payment_date({}, date(2026, 10, 15)) is None
  assert next_payment_date({"day": None}, date(2026, 10, 15)) is None

# ── Refund status ─────────────────────────────────────────────────────────────

def test_the_refund_sensor_reports_the_latest_request():
  # Act
  sensor = build(EDFEnergyRefundStatus)

  # Assert
  assert sensor.native_value == "SUBMITTED"
  assert sensor.extra_state_attributes["amount"] == 250.0
  assert sensor.extra_state_attributes["open_requests"] == 1

def test_the_refund_sensor_reports_what_edf_will_actually_allow():
  # Not the balance - the maximum, which is far lower.
  # Act
  attributes = build(EDFEnergyRefundStatus).extra_state_attributes

  # Assert
  assert attributes["maximum_refund"] == 98.76
  assert attributes["can_request_refund"] == False
  assert attributes["cannot_request_reason"] == "HAS_NOT_GIVEN_READINGS_RECENTLY"

def test_an_account_that_has_never_asked_for_a_refund_says_so():
  # Arrange
  summary = {**SUMMARY, "refund": {**SUMMARY["refund"], "requests": []}}

  # Act
  sensor = build(EDFEnergyRefundStatus, summary)

  # Assert
  assert sensor.native_value == "None requested"
  assert sensor.extra_state_attributes["open_requests"] == 0

def test_a_paid_refund_is_not_counted_as_outstanding():
  # Arrange
  summary = {**SUMMARY, "refund": {**SUMMARY["refund"], "requests": [
    {"id": "1", "amount": 250.0, "payment_date": "2026-09-28", "status": "PAID", "reason": None},
  ]}}

  # Act
  sensor = build(EDFEnergyRefundStatus, summary)

  # Assert
  assert sensor.native_value == "PAID"
  assert sensor.extra_state_attributes["open_requests"] == 0

# ── What the sensors must not carry ───────────────────────────────────────────

def test_no_sensor_puts_a_list_of_statements_or_names_in_its_attributes():
  # Statements, the ledger and the referral list are fetched for the panel and nothing
  # else. If any of them ever reached an attribute it would be written to the recorder on
  # every change, referral names included.
  for cls in (EDFEnergyAccountBalance, EDFEnergyLastBillAmount, EDFEnergyNextPaymentAmount,
              EDFEnergyRefundStatus):
    # Act
    attributes = build(cls).extra_state_attributes

    # Assert
    assert not any(isinstance(value, (list, dict)) for value in attributes.values()), cls.__name__
