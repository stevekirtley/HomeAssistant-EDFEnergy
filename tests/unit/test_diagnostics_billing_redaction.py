"""Billing figures must not leave in a diagnostics download.

Diagnostics get attached to public issues. What an account is in credit by, what the last
bill came to and what the direct debit is are not needed to reproduce a fault, so they are
replaced - while everything that *is* useful for diagnosing those sensors survives.
"""
from custom_components.edf_energy.diagnostics import redact_billing_entity

def entry(state, attributes=None):
  return {
    "state": state,
    "attributes": attributes if attributes is not None else {},
    "last_updated": "2026-10-15T12:00:00+00:00",
    "last_changed": "2026-10-15T12:00:00+00:00",
  }

def test_the_balance_figure_is_removed():
  # Act
  result = redact_billing_entity("edf_energy_a_e351b1a8_account_balance", entry("1234.56"))

  # Assert
  assert result["state"] == "**REDACTED**"

def test_the_bill_amount_and_its_identifiers_are_removed():
  # Act
  result = redact_billing_entity(
    "edf_energy_a_e351b1a8_last_bill_amount",
    entry("57.95", {"bill_id": "117961351", "closing_balance": 5264.46, "issued_date": "2026-10-07"}),
  )

  # Assert
  assert result["state"] == "**REDACTED**"
  assert result["attributes"]["bill_id"] == "**REDACTED**"
  assert result["attributes"]["closing_balance"] == "**REDACTED**"

def test_the_dates_survive_because_they_are_what_diagnose_a_stale_sensor():
  # Act
  result = redact_billing_entity(
    "edf_energy_a_e351b1a8_last_bill_amount",
    entry("57.95", {"issued_date": "2026-10-07", "due_date": "2026-10-22"}),
  )

  # Assert
  assert result["attributes"]["issued_date"] == "2026-10-07"
  assert result["attributes"]["due_date"] == "2026-10-22"
  assert result["last_changed"] == "2026-10-15T12:00:00+00:00"

def test_an_unavailable_sensor_still_reads_as_unavailable():
  # Replacing this would hide the fault the download was taken to investigate.
  for state in ("unavailable", "unknown", None):
    # Act
    result = redact_billing_entity("edf_energy_a_e351b1a8_account_balance", entry(state))

    # Assert
    assert result["state"] == state

def test_the_refund_status_itself_is_kept():
  # It is EDF's own word for where a request has got to, not an amount, and it is the whole
  # point of looking at that sensor.
  # Act
  result = redact_billing_entity(
    "edf_energy_a_e351b1a8_refund_status",
    entry("SUBMITTED", {"amount": 250.0, "cannot_request_reason": "HAS_NOT_GIVEN_READINGS_RECENTLY"}),
  )

  # Assert
  assert result["state"] == "SUBMITTED"
  assert result["attributes"]["amount"] == "**REDACTED**"
  assert result["attributes"]["cannot_request_reason"] == "HAS_NOT_GIVEN_READINGS_RECENTLY"

def test_every_other_entity_is_left_exactly_as_it_was():
  # Arrange
  original = entry("12.4", {"charge_in_kwh": 12.4})

  # Act
  result = redact_billing_entity("edf_energy_a_e351b1a8_previous_accumulative_consumption", original)

  # Assert
  assert result == original
