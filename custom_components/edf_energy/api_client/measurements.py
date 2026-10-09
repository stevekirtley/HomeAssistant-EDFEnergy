"""Half-hourly consumption taken from Kraken's measurements connection.

Raised as issue #43. The REST consumption endpoint is the integration's source for
half-hourly readings and works on every account we have been able to test, export meters
included. One maintainer reports it returning nothing for their export meter, so this is
the second string to the bow: Kraken's own `measurements` connection carries the same
readings, asked for by meter number and direction rather than by meter serial.

REST stays first. It is paged more cheaply, it is what every existing account is already
being served by, and it returns intervals in UTC without a timezone argument to get wrong.
This is only reached when REST has nothing to offer.
"""
from datetime import datetime, timezone

from homeassistant.util.dt import as_utc, parse_datetime

# The direction of flow as Kraken names it. Import is what a normal meter records; export
# is GENERATION, which is the enum spelling that caused some confusion on the issue - the
# type is ReadingDirectionType, not any of the longer names the schema docs suggest.
IMPORT = "CONSUMPTION"
EXPORT = "GENERATION"

# Kraken pages this connection and caps a page well below a day of half hours, so the
# caller has to follow the cursor. 100 is a tidy two days at a time.
PAGE_SIZE = 100

# How far back to look when the caller asked by page size rather than by period. The
# previous-consumption sensors want the latest whole day, and EDF's readings run a day or
# two behind the meter, so three days is the smallest window that reliably holds one.
FALLBACK_DAYS = 3

# Below this, a caller is probing rather than collecting - diagnostics asks for a single
# reading to see whether the endpoint answers - and is not worth a GraphQL round trip.
MINIMUM_PAGE_SIZE = 48

# Half hours are reported against a named timezone rather than an offset, and a reading's
# own startAt comes back with the offset applied. Europe/London keeps the day boundaries
# where a British meter puts them.
TIMEZONE = "Europe/London"

measurements_query = '''query($accountNumber: String!, $startAt: DateTime!, $endAt: DateTime!, $first: Int!, $cursor: String, $mpxn: String!, $direction: ReadingDirectionType!, $timezone: String!) {
  account(accountNumber: $accountNumber) {
    properties {
      measurements(
        first: $first
        after: $cursor
        startAt: $startAt
        endAt: $endAt
        timezone: $timezone
        utilityFilters: [{
          electricityFilters: {
            readingFrequencyType: THIRTY_MIN_INTERVAL
            readingDirection: $direction
            marketSupplyPointId: $mpxn
          }
        }]
      ) {
        pageInfo {
          hasNextPage
          endCursor
        }
        edges {
          node {
            value
            unit
            ... on IntervalMeasurementType {
              startAt
              endAt
            }
          }
        }
      }
    }
  }
}'''


def parse_measurements(response_body, period_from: datetime | None = None, period_to: datetime | None = None) -> list[dict]:
  """Readings from one page, in the same shape the REST consumption endpoint produces.

  Anything without both ends of its interval is dropped: the connection also carries
  running totals, which share the value field but carry no startAt and are not readings.
  """
  account = ((response_body or {}).get("data") or {}).get("account") or {}
  results = []
  for prop in account.get("properties") or []:
    for edge in ((prop or {}).get("measurements") or {}).get("edges") or []:
      node = (edge or {}).get("node") or {}
      start = _as_datetime(node.get("startAt"))
      end = _as_datetime(node.get("endAt"))
      value = _as_float(node.get("value"))
      if start is None or end is None or value is None:
        continue
      # The REST path filters the same way: EDF occasionally answer slightly wider than
      # the window asked for, and a reading outside it would double-count.
      if period_from is not None and start < period_from:
        continue
      if period_to is not None and end > period_to:
        continue
      results.append({"consumption": value, "start": start, "end": end})
  results.sort(key=lambda item: (item["end"].timestamp(), item["end"].fold))
  return results


def next_cursor(response_body) -> str | None:
  """The cursor for the next page, or None when the readings have run out."""
  account = ((response_body or {}).get("data") or {}).get("account") or {}
  for prop in account.get("properties") or []:
    page_info = ((prop or {}).get("measurements") or {}).get("pageInfo") or {}
    if page_info.get("hasNextPage"):
      return page_info.get("endCursor")
  return None


def _as_datetime(value):
  if not value:
    return None
  parsed = parse_datetime(value)
  return as_utc(parsed) if parsed is not None else None


def _as_float(value):
  if value is None:
    return None
  try:
    # Values arrive as decimal strings and sometimes in exponent form - a half hour with
    # nothing exported comes back as "0E-18" rather than "0".
    return float(value)
  except (TypeError, ValueError):
    return None

