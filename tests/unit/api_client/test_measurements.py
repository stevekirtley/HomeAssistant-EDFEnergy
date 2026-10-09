"""Reading half-hourly consumption from Kraken when REST has nothing (issue #43).

The payloads here are shaped exactly as a live account answered on 9 October 2026,
including the two details that caught us out: values arrive as decimal strings, in
exponent form when the half hour recorded nothing, and startAt/endAt live on an inline
fragment so a reading that isn't an interval carries neither.
"""
from datetime import datetime, timezone

import pytest

from custom_components.edf_energy.api_client.measurements import (
  EXPORT,
  IMPORT,
  next_cursor,
  parse_measurements,
)

PERIOD_FROM = datetime(2026, 10, 6, 0, 0, tzinfo=timezone.utc)
PERIOD_TO = datetime(2026, 10, 7, 0, 0, tzinfo=timezone.utc)


def response(nodes, has_next_page=False, end_cursor=None):
  return {
    "data": {
      "account": {
        "properties": [
          {
            "measurements": {
              "pageInfo": {"hasNextPage": has_next_page, "endCursor": end_cursor},
              "edges": [{"node": node} for node in nodes],
            },
          },
        ],
      },
    },
  }


def reading(start, end, value):
  return {"value": value, "unit": "kwh", "startAt": start, "endAt": end}


def test_the_enum_spellings_are_the_ones_kraken_accepts():
  """Guessed at on the issue; these came from introspecting ReadingDirectionType."""
  assert IMPORT == "CONSUMPTION"
  assert EXPORT == "GENERATION"


def test_readings_come_out_in_the_rest_endpoint_s_shape():
  """Same keys and the same UTC datetimes, so nothing downstream can tell them apart."""
  body = response([
    reading("2026-10-06T01:00:00+01:00", "2026-10-06T01:30:00+01:00", "0.0120000"),
    reading("2026-10-06T01:30:00+01:00", "2026-10-06T02:00:00+01:00", "1.4500000"),
  ])

  results = parse_measurements(body, PERIOD_FROM, PERIOD_TO)

  assert results == [
    {"consumption": 0.012, "start": datetime(2026, 10, 6, 0, 0, tzinfo=timezone.utc), "end": datetime(2026, 10, 6, 0, 30, tzinfo=timezone.utc)},
    {"consumption": 1.45, "start": datetime(2026, 10, 6, 0, 30, tzinfo=timezone.utc), "end": datetime(2026, 10, 6, 1, 0, tzinfo=timezone.utc)},
  ]


def test_an_empty_half_hour_reads_as_zero_not_as_missing():
  """A night with no export comes back as "0E-18", which float() copes with and int() doesn't."""
  body = response([reading("2026-10-06T01:00:00+01:00", "2026-10-06T01:30:00+01:00", "0E-18")])

  results = parse_measurements(body, PERIOD_FROM, PERIOD_TO)

  assert len(results) == 1
  assert results[0]["consumption"] == 0.0


def test_readings_are_sorted_by_the_end_of_their_interval():
  body = response([
    reading("2026-10-06T03:00:00+01:00", "2026-10-06T03:30:00+01:00", "3"),
    reading("2026-10-06T01:00:00+01:00", "2026-10-06T01:30:00+01:00", "1"),
    reading("2026-10-06T02:00:00+01:00", "2026-10-06T02:30:00+01:00", "2"),
  ])

  results = parse_measurements(body, PERIOD_FROM, PERIOD_TO)

  assert [r["consumption"] for r in results] == [1.0, 2.0, 3.0]


def test_anything_outside_the_window_is_dropped():
  """EDF answer a little wider than asked at times, and the REST path filters the same way."""
  body = response([
    reading("2026-10-05T23:00:00+01:00", "2026-10-05T23:30:00+01:00", "9"),
    reading("2026-10-06T01:00:00+01:00", "2026-10-06T01:30:00+01:00", "1"),
    reading("2026-10-07T01:00:00+01:00", "2026-10-07T01:30:00+01:00", "9"),
  ])

  results = parse_measurements(body, PERIOD_FROM, PERIOD_TO)

  assert [r["consumption"] for r in results] == [1.0]


def test_a_node_that_is_not_an_interval_is_skipped():
  """The connection also carries running totals: a value, but no interval to put it in."""
  body = response([
    {"value": "123.45", "unit": "kwh"},
    reading("2026-10-06T01:00:00+01:00", "2026-10-06T01:30:00+01:00", "1"),
  ])

  results = parse_measurements(body, PERIOD_FROM, PERIOD_TO)

  assert [r["consumption"] for r in results] == [1.0]


def test_without_a_window_everything_is_kept():
  body = response([reading("2026-10-06T01:00:00+01:00", "2026-10-06T01:30:00+01:00", "1")])

  assert len(parse_measurements(body)) == 1


@pytest.mark.parametrize("body", [None, {}, {"data": None}, {"data": {"account": None}},
                                  {"data": {"account": {"properties": None}}},
                                  {"data": {"account": {"properties": [None]}}},
                                  response([None]), response([{}])])
def test_a_useless_response_is_no_readings_rather_than_an_error(body):
  assert parse_measurements(body, PERIOD_FROM, PERIOD_TO) == []


def test_the_cursor_is_handed_back_while_there_are_more_pages():
  body = response([], has_next_page=True, end_cursor="YXJyYXljb25uZWN0aW9uOjQ3")

  assert next_cursor(body) == "YXJyYXljb25uZWN0aW9uOjQ3"


def test_the_last_page_hands_back_no_cursor():
  """Ending the loop on hasNextPage rather than on an empty page: EDF return the final
  cursor either way, and following it again would fetch the same page for ever."""
  body = response([], has_next_page=False, end_cursor="YXJyYXljb25uZWN0aW9uOjQ3")

  assert next_cursor(body) is None


@pytest.mark.parametrize("body", [None, {}, response([])])
def test_a_useless_response_has_no_cursor(body):
  assert next_cursor(body) is None
