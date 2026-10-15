"""Parsing the billing, ledger, referral and refund payloads.

The responses below are trimmed copies of what the live API served in October 2026, so a
rename at EDF's end shows up here rather than as a blank card in the panel.
"""
import pytest

from custom_components.edf_energy.api_client.billing import (
  build_idempotency_key,
  parse_bill_attachment,
  parse_billing_summary,
  parse_bills,
  parse_referrals,
  parse_repayment_request,
  parse_transactions,
  to_pounds,
)
from datetime import datetime, timezone

SUMMARY_RESPONSE = {"data": {"account": {
  "balance": 123456,
  "status": "ACTIVE",
  "paymentSchedules": {"edges": [{"node": {
    "id": "20309817", "paymentAmount": 0, "paymentDay": 1, "paymentFrequency": "Monthly",
    "isVariablePaymentAmount": True, "validFrom": "2026-07-09", "validTo": None,
    "scheduleType": "DIRECT_DEBIT",
  }}]},
  "bills": {"edges": [{"node": {
    "id": "117961351", "billType": "STATEMENT", "fromDate": "2026-09-14", "toDate": "2026-10-06",
    "issuedDate": "2026-10-07", "closingBalance": 526446, "paymentDueDate": "2026-10-22",
    "totalCharges": {"grossTotal": 5795},
  }}]},
  "requestRefundEligibility": {"canRequestRefund": False, "reason": "HAS_NOT_GIVEN_READINGS_RECENTLY"},
  "maximumRefund": {"amount": 9876, "reasonToRecommendAmount": "TOTAL_AMOUNT_PAID_VIA_ACTIVE_DDI",
                    "recommendedBalance": 10172},
  "repayments": {"edges": [
    {"node": {"id": "2443432", "amount": 25000, "paymentDate": "2026-10-14", "status": "SUBMITTED",
              "reason": "PARTIAL_CREDIT_REFUND"}},
    {"node": {"id": "2403503", "amount": 25000, "paymentDate": "2026-09-28", "status": "PAID",
              "reason": "PARTIAL_CREDIT_REFUND"}},
  ]},
}}}

# ── Amounts ───────────────────────────────────────────────────────────────────

def test_amounts_are_pence_and_come_out_as_pounds():
  # Arrange / Act
  result = parse_billing_summary(SUMMARY_RESPONSE)

  # Assert
  assert result["balance"] == 1234.56
  assert result["last_bill"]["amount"] == 57.95
  assert result["refund"]["maximum"] == 98.76

def test_a_missing_amount_stays_missing_rather_than_becoming_zero():
  # A zero and an absence mean different things on a bill, so they are not conflated.
  assert to_pounds(None) is None
  assert to_pounds(0) == 0

# ── Billing summary ───────────────────────────────────────────────────────────

def test_the_latest_statement_carries_its_dates():
  # Act
  bill = parse_billing_summary(SUMMARY_RESPONSE)["last_bill"]

  # Assert
  assert bill["issued_date"] == "2026-10-07"
  assert bill["from_date"] == "2026-09-14"
  assert bill["due_date"] == "2026-10-22"
  assert bill["closing_balance"] == 5264.46

def test_a_variable_schedule_is_flagged_as_such():
  # EDF collect whatever the period came to, and paymentAmount is then 0 and meaningless.
  # Act
  schedule = parse_billing_summary(SUMMARY_RESPONSE)["payment_schedule"]

  # Assert
  assert schedule["is_variable"] == True
  assert schedule["day"] == 1

def test_the_refund_reason_is_passed_through_as_edf_word_it():
  # Act
  refund = parse_billing_summary(SUMMARY_RESPONSE)["refund"]

  # Assert
  assert refund["can_request"] == False
  assert refund["reason"] == "HAS_NOT_GIVEN_READINGS_RECENTLY"

def test_the_maximum_refund_is_not_the_balance():
  # The whole point of asking for maximumRefund: EDF only refund what has been paid in by
  # direct debit, so offering the balance would be wrong by an order of magnitude.
  # Act
  result = parse_billing_summary(SUMMARY_RESPONSE)

  # Assert
  assert result["refund"]["maximum"] < result["balance"]

def test_refund_requests_come_through_newest_first_with_their_status():
  # Act
  requests = parse_billing_summary(SUMMARY_RESPONSE)["refund"]["requests"]

  # Assert
  assert [r["status"] for r in requests] == ["SUBMITTED", "PAID"]
  assert requests[0]["amount"] == 250.0

def test_an_account_with_no_billing_history_parses_rather_than_raising():
  # Arrange
  response = {"data": {"account": {"balance": 0, "status": "ACTIVE", "paymentSchedules": {"edges": []},
                                   "bills": {"edges": []}, "repayments": {"edges": []}}}}

  # Act
  result = parse_billing_summary(response)

  # Assert
  assert result["last_bill"] is None
  assert result["payment_schedule"] is None
  assert result["refund"]["requests"] == []

def test_nothing_at_all_is_not_mistaken_for_an_empty_account():
  assert parse_billing_summary(None) is None
  assert parse_billing_summary({"data": {"account": None}}) is None

# ── Statements ────────────────────────────────────────────────────────────────

BILLS_RESPONSE = {"data": {"account": {"bills": {
  "pageInfo": {"endCursor": "YXJyYXljb25uZWN0aW9uOjI=", "hasNextPage": True},
  "edges": [
    {"node": {"id": "117961351", "billType": "STATEMENT", "fromDate": "2026-09-14", "toDate": "2026-10-06",
              "issuedDate": "2026-10-07", "closingBalance": 526446, "openingBalance": 482241,
              "paymentDueDate": "2026-10-22", "status": "CLOSED", "isFinal": False,
              "totalCharges": {"grossTotal": 5795}, "totalCredits": {"grossTotal": 75000}}},
    {"node": {"id": "117260615", "billType": "STATEMENT", "fromDate": "2026-09-07", "toDate": "2026-09-13",
              "issuedDate": "2026-09-14", "closingBalance": 482241, "openingBalance": 470741,
              "paymentDueDate": "2026-09-29", "status": "CLOSED", "isFinal": False,
              "totalCharges": {"grossTotal": 0}, "totalCredits": {"grossTotal": 11500}}},
  ],
}}}}

def test_the_statement_list_keeps_the_cursor_so_older_ones_can_be_asked_for():
  # Act
  result = parse_bills(BILLS_RESPONSE)

  # Assert
  assert len(result["bills"]) == 2
  assert result["has_more"] == True
  assert result["cursor"] == "YXJyYXljb25uZWN0aW9uOjI="

def test_a_statement_carries_its_type_so_the_pdf_can_be_asked_for_later():
  # bill(id:) answers null without the type, so the list has to hand it back.
  # Act
  bill = parse_bills(BILLS_RESPONSE)["bills"][0]

  # Assert
  assert bill["bill_type"] == "STATEMENT"
  assert bill["charges"] == 57.95
  assert bill["credits"] == 750.0

def test_no_statement_link_comes_back_with_the_list():
  # The links expire within the hour, so they are fetched one at a time on demand. If one
  # ever appears in the list payload it would end up cached and dead.
  # Act
  result = parse_bills(BILLS_RESPONSE)

  # Assert
  assert all("url" not in bill for bill in result["bills"])

# ── Statement PDF ─────────────────────────────────────────────────────────────

def test_the_statement_link_comes_back_with_its_expiry():
  # Arrange
  response = {"data": {"account": {"bill": {"id": "117961351", "attachments": {"edges": [{"node": {
    "filename": "statement.pdf", "temporaryUrl": "https://example.invalid/s.pdf?sig=x",
    "temporaryUrlExpiresAt": "2026-10-15T13:00:00+00:00",
  }}]}}}}}

  # Act
  result = parse_bill_attachment(response)

  # Assert
  assert result["url"] == "https://example.invalid/s.pdf?sig=x"
  assert result["expires_at"] == "2026-10-15T13:00:00+00:00"

def test_a_statement_with_no_document_attached_is_not_an_error():
  # Arrange
  response = {"data": {"account": {"bill": {"id": "1", "attachments": {"edges": []}}}}}

  # Act / Assert
  assert parse_bill_attachment(response) is None

def test_a_bill_asked_for_without_its_type_answers_nothing():
  # This is what the API actually does, and it is worth pinning: it is not an auth problem.
  # Arrange
  response = {"data": {"account": {"bill": None}}}

  # Act / Assert
  assert parse_bill_attachment(response) is None

# ── Ledger ────────────────────────────────────────────────────────────────────

TRANSACTIONS_RESPONSE = {"data": {"account": {"transactions": {
  "pageInfo": {"endCursor": "YXJyYXljb25uZWN0aW9uOjQ=", "hasNextPage": True},
  "edges": [
    {"node": {"__typename": "Credit", "id": "10498741299", "title": "Referring account referral reward",
              "note": "Credit for referring A-5E6F7A8B", "reasonCode": "REFERRING_ACCOUNT_REFERRAL_REWARD",
              "amount": 10000, "postedDate": "2026-10-14", "createdAt": "2026-10-14T06:06:12.364587+00:00",
              "balanceCarriedForward": 123456, "billingDocumentIdentifier": "120309355",
              "isHeld": False, "isIssued": False, "isReversed": False, "hasStatement": True}},
    {"node": {"__typename": "Charge", "id": "10400000000", "title": "Electricity", "note": None,
              "reasonCode": None, "amount": 5795, "postedDate": "2026-10-06",
              "createdAt": "2026-10-06T06:00:00+00:00", "balanceCarriedForward": 526446,
              "billingDocumentIdentifier": None, "isHeld": False, "isIssued": True,
              "isReversed": False, "hasStatement": True}},
    {"node": {"__typename": "Payment", "id": "10300000000", "title": "Direct debit", "amount": 15000,
              "postedDate": "2026-10-01", "createdAt": "2026-10-01T06:00:00+00:00",
              "balanceCarriedForward": 470741}},
    {"node": {"__typename": "Refund", "id": "10200000000", "title": "Refund", "amount": 25000,
              "postedDate": "2026-09-28", "createdAt": "2026-09-28T06:00:00+00:00",
              "balanceCarriedForward": 455741}},
  ],
}}}}

def test_charges_and_refunds_are_signed_against_the_account():
  # Kraken report every amount positive and leave the direction to the type, so a column of
  # them is meaningless until it is signed.
  # Act
  transactions = parse_transactions(TRANSACTIONS_RESPONSE)["transactions"]
  by_type = {t["type"]: t for t in transactions}

  # Assert
  assert by_type["Credit"]["signed_amount"] == 100.0
  assert by_type["Payment"]["signed_amount"] == 150.0
  assert by_type["Charge"]["signed_amount"] == -57.95
  assert by_type["Refund"]["signed_amount"] == -250.0

def test_the_unsigned_amount_is_kept_alongside_the_signed_one():
  # Act
  charge = next(t for t in parse_transactions(TRANSACTIONS_RESPONSE)["transactions"] if t["type"] == "Charge")

  # Assert
  assert charge["amount"] == 57.95
  assert charge["signed_amount"] == -57.95

def test_an_unknown_transaction_type_still_parses():
  # A type we have not seen is shown rather than dropped, treated as money in.
  # Arrange
  response = {"data": {"account": {"transactions": {"pageInfo": {}, "edges": [{"node": {
    "__typename": "SomethingNew", "id": "1", "title": "Mystery", "amount": 1000,
    "postedDate": "2026-10-01",
  }}]}}}}

  # Act
  transaction = parse_transactions(response)["transactions"][0]

  # Assert
  assert transaction["type"] == "SomethingNew"
  assert transaction["signed_amount"] == 10.0

def test_the_running_balance_is_kept_so_the_ledger_can_be_checked():
  # Act
  transactions = parse_transactions(TRANSACTIONS_RESPONSE)["transactions"]

  # Assert
  assert transactions[0]["balance_carried_forward"] == 1234.56

# ── Referrals ─────────────────────────────────────────────────────────────────

REFERRALS_RESPONSE = {"data": {"account": {
  "referralsCreated": 92,
  "activeReferralSchemes": {"domestic": {
    "code": "RAF FROM 7 OCT 2026",
    "referralUrl": "https://edfenergy.com/quote/refer-a-friend/massive-sun-7007",
    "referralDisplayUrl": "edfenergy.com/quote/refer-a-friend/massive-sun-7007",
    "referrerRewardAmount": 5000, "referredRewardAmount": 5000, "combinedRewardAmount": 10000,
  }},
  "referrals": {
    "totalCount": 92, "referringUserTotalPaymentAmount": 730000,
    "edges": [
      {"node": {"id": "214769", "code": "RAFBOOSTSEP26", "schemeType": "REFERRAL_REWARD",
                "referredUserName": "A Name", "referredUserJoinDate": "2026-09-24T22:29:56+00:00",
                "paymentStatus": "Paid", "paymentDate": "2026-10-14",
                "referringUserPaymentAmount": 10000, "combinedPaymentAmount": 17500}},
      {"node": {"id": "220562", "code": "RAF FROM 7 OCT 2026", "schemeType": "REFERRAL_REWARD",
                "referredUserName": "Another Name", "referredUserJoinDate": "2026-10-10T15:03:41+00:00",
                "paymentStatus": "Switch in progress", "paymentDate": None,
                "referringUserPaymentAmount": 5000, "combinedPaymentAmount": 10000}},
    ],
  },
}}}

def test_the_referral_scheme_and_the_total_earned_come_through():
  # Act
  result = parse_referrals(REFERRALS_RESPONSE)

  # Assert
  assert result["scheme"]["referrer_reward"] == 50.0
  assert result["total"] == 92
  assert result["total_earned"] == 7300.0

def test_an_unpaid_referral_keeps_edfs_own_status_wording():
  # These are free text rather than enum codes - "Switch in progress" - so they are shown
  # as given rather than being mapped to a guess.
  # Act
  referrals = parse_referrals(REFERRALS_RESPONSE)["referrals"]

  # Assert
  assert referrals[1]["status"] == "Switch in progress"
  assert referrals[1]["payment_date"] is None

def test_an_account_that_has_referred_nobody_still_gets_its_link():
  # Arrange
  response = {"data": {"account": {
    "referralsCreated": 0,
    "activeReferralSchemes": {"domestic": {"referralUrl": "https://example.invalid/r",
                                           "referrerRewardAmount": 5000}},
    "referrals": {"totalCount": 0, "edges": []},
  }}}

  # Act
  result = parse_referrals(response)

  # Assert
  assert result["referrals"] == []
  assert result["scheme"]["url"] == "https://example.invalid/r"

# ── Refund request ────────────────────────────────────────────────────────────

def test_a_submitted_refund_is_acknowledged_with_an_id_and_a_status():
  # The output type carries only these two - asking for anything else is a 400.
  # Arrange
  response = {"data": {"submitRepaymentRequest": {"repaymentRequest": {
    "requestId": "abc-123", "status": "REQUESTED",
  }}}}

  # Act
  result = parse_repayment_request(response)

  # Assert
  assert result == {"request_id": "abc-123", "status": "REQUESTED"}

def test_a_refund_that_was_not_acknowledged_is_not_reported_as_submitted():
  assert parse_repayment_request({"data": {"submitRepaymentRequest": None}}) is None
  assert parse_repayment_request(None) is None

def test_the_same_refund_asked_for_twice_in_a_day_carries_the_same_key():
  # Kraken enforce the key server side, so this is what stops a double tap paying out twice.
  # Arrange
  current = datetime(2026, 10, 15, 9, 30, tzinfo=timezone.utc)
  later = datetime(2026, 10, 15, 21, 45, tzinfo=timezone.utc)

  # Act / Assert
  assert build_idempotency_key("A-1A2B3C4D", 25000, current) == build_idempotency_key("A-1A2B3C4D", 25000, later)

def test_a_different_amount_is_a_different_request():
  # Arrange
  current = datetime(2026, 10, 15, 9, 30, tzinfo=timezone.utc)

  # Act / Assert
  assert build_idempotency_key("A-1A2B3C4D", 25000, current) != build_idempotency_key("A-1A2B3C4D", 10000, current)
