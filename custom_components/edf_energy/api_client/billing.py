"""Billing, transactions, referrals and refunds from Kraken.

Everything the account tab shows about money comes from here. The queries were taken from
the EDF app's own traffic and then confirmed field by field against the live schema, so
the shapes below are what the API actually serves rather than what the docs imply.

Two things to know before changing anything in this file:

Every amount Kraken returns is in **minor units** - pence - as an integer. A balance of
123456 is £1,234.10. Each parser converts on the way out so nothing downstream has to
remember, and `to_pounds` is the only place that division lives.

A bill's PDF is a **short lived pre-signed S3 link**. It arrives with an expiry attached
and is only fetched when somebody asks to open that bill, never stored alongside the bill
list and never written to an attribute or the recorder. A cached one would be a dead link
within the hour, and a link that outlives the panel session is a copy of the customer's
statement sitting somewhere it was not asked to be.
"""
from datetime import datetime

from homeassistant.util.dt import parse_datetime

# Statements can only be asked for one at a time by giving their type as well as their id.
# `bill(id:)` on its own answers null, which is what sent the first attempt at this round
# in circles - it is not an authorisation problem, the argument is simply not optional.
BILL_TYPES = ("STATEMENT", "INVOICE", "PRE_KRAKEN_BILL", "PERIOD_BASED_DOCUMENT", "CREDIT_NOTE")

# A page of bills, transactions or referrals. EDF page all three and these are a year or
# so of each, which is as much as the panel shows without being asked for more.
BILLS_PAGE_SIZE = 24
TRANSACTIONS_PAGE_SIZE = 50
REFERRALS_PAGE_SIZE = 100


billing_summary_query = '''query($accountNumber: String!) {
  account(accountNumber: $accountNumber) {
    balance
    status
    paymentSchedules(first: 1, active: true) {
      edges {
        node {
          id
          paymentAmount
          paymentDay
          paymentFrequency
          isVariablePaymentAmount
          validFrom
          validTo
          scheduleType
        }
      }
    }
    bills(first: 1) {
      edges {
        node {
          id
          billType
          fromDate
          toDate
          issuedDate
          ... on StatementType {
            closingBalance
            paymentDueDate
            totalCharges { grossTotal }
          }
        }
      }
    }
    requestRefundEligibility {
      canRequestRefund
      reason
    }
    maximumRefund {
      amount
      reasonToRecommendAmount
      recommendedBalance
    }
    repayments(first: 10) {
      edges {
        node {
          id
          amount
          paymentDate
          status
          reason
        }
      }
    }
  }
}'''

bills_query = '''query($accountNumber: String!, $first: Int!, $cursor: String) {
  account(accountNumber: $accountNumber) {
    bills(first: $first, after: $cursor) {
      pageInfo { endCursor hasNextPage }
      edges {
        node {
          id
          billType
          fromDate
          toDate
          issuedDate
          ... on StatementType {
            openingBalance
            closingBalance
            paymentDueDate
            status
            isFinal
            totalCharges { grossTotal }
            totalCredits { grossTotal }
          }
        }
      }
    }
  }
}'''

bill_attachment_query = '''query($accountNumber: String!, $billId: ID!, $billType: BillTypeEnum!) {
  account(accountNumber: $accountNumber) {
    bill(id: $billId, billType: $billType) {
      id
      attachments {
        edges {
          node {
            filename
            temporaryUrl
            temporaryUrlExpiresAt
          }
        }
      }
    }
  }
}'''

transactions_query = '''query($accountNumber: String!, $first: Int!, $cursor: String) {
  account(accountNumber: $accountNumber) {
    transactions(first: $first, after: $cursor) {
      pageInfo { endCursor hasNextPage }
      edges {
        node {
          __typename
          id
          title
          note
          reasonCode
          amount
          postedDate
          createdAt
          balanceCarriedForward
          billingDocumentIdentifier
          isHeld
          isIssued
          isReversed
          hasStatement
        }
      }
    }
  }
}'''

referrals_query = '''query($accountNumber: String!, $first: Int!) {
  account(accountNumber: $accountNumber) {
    referralsCreated
    activeReferralSchemes {
      domestic {
        code
        referralUrl
        referralDisplayUrl
        referrerRewardAmount
        referredRewardAmount
        combinedRewardAmount
      }
    }
    referrals(first: $first) {
      totalCount
      referringUserTotalPaymentAmount
      edges {
        node {
          id
          code
          schemeType
          referredUserName
          referredUserJoinDate
          paymentStatus
          paymentDate
          referringUserPaymentAmount
          combinedPaymentAmount
        }
      }
    }
  }
}'''

# Asking for anything beyond requestId and status is a 400: the output type carries only
# those two. The idempotency key is enforced server side, so a repeat of the same request
# is refused rather than paying out twice.
submit_repayment_mutation = '''mutation($input: RequestRepaymentInputType!) {
  submitRepaymentRequest(input: $input) {
    repaymentRequest {
      requestId
      status
    }
  }
}'''


def to_pounds(minor_units) -> float | None:
  """Pence as an integer to pounds, which is how every amount here arrives."""
  if minor_units is None:
    return None
  try:
    return round(int(minor_units) / 100, 2)
  except (TypeError, ValueError):
    return None


def _nodes(connection) -> list:
  """The nodes of a Relay connection, tolerating every level of it being absent."""
  if not connection:
    return []
  return [edge.get("node") for edge in connection.get("edges") or [] if edge and edge.get("node")]


def _account(response) -> dict | None:
  if not response or not isinstance(response, dict):
    return None
  account = (response.get("data") or {}).get("account")
  return account if isinstance(account, dict) else None


def parse_billing_summary(response) -> dict | None:
  """Balance, the latest statement, the payment schedule and the refund position.

  One query feeds all four sensors and the account tab's header, because each piece on its
  own is a round trip for a single number and they are only ever shown together.
  """
  account = _account(response)
  if account is None:
    return None

  schedule = next(iter(_nodes(account.get("paymentSchedules"))), None)
  bill = next(iter(_nodes(account.get("bills"))), None)
  eligibility = account.get("requestRefundEligibility") or {}
  maximum = account.get("maximumRefund") or {}
  repayments = [{
    "id": node.get("id"),
    "amount": to_pounds(node.get("amount")),
    "payment_date": node.get("paymentDate"),
    "status": node.get("status"),
    "reason": node.get("reason"),
  } for node in _nodes(account.get("repayments"))]

  return {
    # A credit balance is the normal state for an account in hand, and EDF report it
    # positive. It is passed through as given rather than signed, so it reads the same way
    # round as it does in the app and on the bill.
    "balance": to_pounds(account.get("balance")),
    "status": account.get("status"),
    "last_bill": {
      "id": bill.get("id"),
      "bill_type": bill.get("billType"),
      "from_date": bill.get("fromDate"),
      "to_date": bill.get("toDate"),
      "issued_date": bill.get("issuedDate"),
      "due_date": bill.get("paymentDueDate"),
      "closing_balance": to_pounds(bill.get("closingBalance")),
      "amount": to_pounds((bill.get("totalCharges") or {}).get("grossTotal")),
    } if bill is not None else None,
    "payment_schedule": {
      "amount": to_pounds(schedule.get("paymentAmount")),
      "day": schedule.get("paymentDay"),
      "frequency": schedule.get("paymentFrequency"),
      # A variable schedule is EDF collecting whatever the period came to rather than a
      # fixed monthly figure, in which case paymentAmount is 0 and means nothing.
      "is_variable": schedule.get("isVariablePaymentAmount"),
      "type": schedule.get("scheduleType"),
      "valid_from": schedule.get("validFrom"),
      "valid_to": schedule.get("validTo"),
    } if schedule is not None else None,
    "refund": {
      "can_request": eligibility.get("canRequestRefund"),
      # EDF's own reason code, e.g. HAS_NOT_GIVEN_READINGS_RECENTLY. Shown as given, since
      # rewording it would mean guessing at codes we have not seen.
      "reason": eligibility.get("reason"),
      # Well below the balance - £273 against £1,234 on the account this was built from -
      # because EDF only refund what has been paid in by direct debit. Never offer the
      # balance as refundable.
      "maximum": to_pounds(maximum.get("amount")),
      "maximum_reason": maximum.get("reasonToRecommendAmount"),
      "recommended_balance": to_pounds(maximum.get("recommendedBalance")),
      "requests": repayments,
    },
  }


def parse_bills(response) -> dict | None:
  """The statement list, newest first, with no attachment links in it."""
  account = _account(response)
  if account is None:
    return None

  connection = account.get("bills") or {}
  page_info = connection.get("pageInfo") or {}

  return {
    "bills": [{
      "id": node.get("id"),
      "bill_type": node.get("billType"),
      "from_date": node.get("fromDate"),
      "to_date": node.get("toDate"),
      "issued_date": node.get("issuedDate"),
      "due_date": node.get("paymentDueDate"),
      "opening_balance": to_pounds(node.get("openingBalance")),
      "closing_balance": to_pounds(node.get("closingBalance")),
      "charges": to_pounds((node.get("totalCharges") or {}).get("grossTotal")),
      "credits": to_pounds((node.get("totalCredits") or {}).get("grossTotal")),
      "status": node.get("status"),
      "is_final": node.get("isFinal"),
    } for node in _nodes(connection)],
    "cursor": page_info.get("endCursor"),
    "has_more": page_info.get("hasNextPage") == True,
  }


def parse_bill_attachment(response) -> dict | None:
  """The pre-signed link for one statement, and when it stops working.

  Handed straight to the browser and kept nowhere. See the note at the top of the file.
  """
  account = _account(response)
  if account is None:
    return None

  bill = account.get("bill")
  if not bill:
    return None

  attachment = next(iter(_nodes(bill.get("attachments"))), None)
  if attachment is None or not attachment.get("temporaryUrl"):
    return None

  return {
    "url": attachment.get("temporaryUrl"),
    "filename": attachment.get("filename"),
    "expires_at": attachment.get("temporaryUrlExpiresAt"),
  }


# How each kind of ledger entry moves the balance. Kraken reports every amount positive
# and leaves the direction to the type, so a charge of 5795 and a payment of 5795 are the
# same number pulling opposite ways.
TRANSACTION_DIRECTION = {
  "Charge": -1,
  "Payment": 1,
  "Credit": 1,
  "Refund": -1,
}


def parse_transactions(response) -> dict | None:
  """The account ledger, newest first, with each entry signed by its type."""
  account = _account(response)
  if account is None:
    return None

  connection = account.get("transactions") or {}
  page_info = connection.get("pageInfo") or {}

  transactions = []
  for node in _nodes(connection):
    kind = node.get("__typename")
    amount = to_pounds(node.get("amount"))
    direction = TRANSACTION_DIRECTION.get(kind, 1)
    created_at = parse_datetime(node.get("createdAt")) if node.get("createdAt") else None

    transactions.append({
      "id": node.get("id"),
      "type": kind,
      "title": node.get("title"),
      "note": node.get("note"),
      "reason_code": node.get("reasonCode"),
      "amount": amount,
      # Signed for display, so a list of them reads like a statement rather than a column
      # of positive numbers that all have to be interpreted by their label.
      "signed_amount": round(amount * direction, 2) if amount is not None else None,
      "posted_date": node.get("postedDate"),
      "created_at": created_at.isoformat() if created_at is not None else node.get("createdAt"),
      "balance_carried_forward": to_pounds(node.get("balanceCarriedForward")),
      "document_id": node.get("billingDocumentIdentifier"),
      "is_held": node.get("isHeld"),
      "is_issued": node.get("isIssued"),
      "is_reversed": node.get("isReversed"),
      "has_statement": node.get("hasStatement"),
    })

  return {
    "transactions": transactions,
    "cursor": page_info.get("endCursor"),
    "has_more": page_info.get("hasNextPage") == True,
  }


def parse_referrals(response) -> dict | None:
  """Who has joined on the account's referral link, and what each one paid out.

  The names here are other people's, which is why none of this is ever written to an
  entity, an attribute or the recorder - it is fetched when the tab is open and rendered.
  """
  account = _account(response)
  if account is None:
    return None

  scheme = (account.get("activeReferralSchemes") or {}).get("domestic") or {}
  connection = account.get("referrals") or {}

  referrals = [{
    "id": node.get("id"),
    "code": node.get("code"),
    "name": node.get("referredUserName"),
    "joined": node.get("referredUserJoinDate"),
    # EDF's own words rather than a code here - "Paid", "Switch in progress" - so they are
    # shown as given.
    "status": node.get("paymentStatus"),
    "payment_date": node.get("paymentDate"),
    "reward": to_pounds(node.get("referringUserPaymentAmount")),
    "combined_reward": to_pounds(node.get("combinedPaymentAmount")),
  } for node in _nodes(connection)]

  return {
    "scheme": {
      "code": scheme.get("code"),
      "url": scheme.get("referralUrl"),
      "display_url": scheme.get("referralDisplayUrl"),
      "referrer_reward": to_pounds(scheme.get("referrerRewardAmount")),
      "referred_reward": to_pounds(scheme.get("referredRewardAmount")),
      "combined_reward": to_pounds(scheme.get("combinedRewardAmount")),
    } if scheme else None,
    "referrals": referrals,
    "total": connection.get("totalCount") if connection.get("totalCount") is not None else account.get("referralsCreated"),
    "total_earned": to_pounds(connection.get("referringUserTotalPaymentAmount")),
  }


def parse_repayment_request(response) -> dict | None:
  """The acknowledgement of a submitted refund request: an id and a status, nothing else."""
  if not response or not isinstance(response, dict):
    return None

  submitted = (response.get("data") or {}).get("submitRepaymentRequest") or {}
  request = submitted.get("repaymentRequest") or {}
  if not request.get("requestId"):
    return None

  return {
    "request_id": request.get("requestId"),
    "status": request.get("status"),
  }


def build_idempotency_key(account_id: str, amount_in_pence: int, current: datetime) -> str:
  """A key EDF will accept once.

  Kraken enforces these server side and answers KT-CT-3928 if the same key comes back with
  a different amount, so it is built from the account, the amount and the day rather than
  being random: a double tap on the panel's button is then the same request rather than a
  second refund.
  """
  return f"{account_id}-{amount_in_pence}-{current.strftime('%Y%m%d')}"
