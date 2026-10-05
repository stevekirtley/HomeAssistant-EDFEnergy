"""Booking, moving and cancelling Flextras free hours.

The payloads are the real ones from the 5 October 2026 app capture. The request bodies
asserted here were compared byte-for-byte against what the app actually sent, which is
what makes them worth asserting: EDF's booking call replaces the whole set at once, so a
body that is subtly wrong cancels hours rather than failing loudly.
"""
from datetime import datetime, timezone

import pytest

from custom_components.edf_energy.api_client.flextras_hours import (
  booking_payload,
  booking_window,
  parse_bookable_days,
  parse_booked_hours,
  parse_booking_result,
  parse_day_slots,
  slot_id,
)
from custom_components.edf_energy.const import DATA_CLIENT, DATA_FLEXTRAS_HOURS, DOMAIN
from custom_components.edf_energy.coordinators.flextras_hours import (
  apply_mode,
  async_book_flextras_hours,
  normalise_hour,
)

ACCOUNT_ID = "A-XXXXXX"
PROPERTY_ID = "4650459"

SELECT_DAYS = {"screen": "CLUB_FLEX_BOOK_HOURS", "components": [{
  "type": "SELECT_DAYS_LIST", "props": {"months": [
    {"month": "October", "year": 2026, "days": [
      {"date": "2026-10-10", "day": "Saturday", "isAvailable": True},
      {"date": "2026-10-11", "day": "Sunday", "isAvailable": True},
      {"date": "2026-10-17", "day": "Saturday", "isAvailable": False},
    ]},
    {"month": "November", "year": 2026, "days": [
      {"date": "2026-11-01", "day": "Sunday", "isAvailable": True},
    ]},
  ]},
}]}


def day_slots(date, selected=()):
  return {"accountNumber": ACCOUNT_ID, "propertyId": PROPERTY_ID, "slots": [
    {"slotId": f"SLOT-{date}-{h:02d}-{h + 1:02d}", "date": date,
     "startTime": f"{h:02d}:00", "endTime": f"{h + 1:02d}:00",
     "status": "SELECTED" if f"{h:02d}:00" in selected else "AVAILABLE"}
    for h in range(15)
  ]}


def hours_screen(slots, remaining=4):
  items = [{"rawTimeSlots": [
    {"slotId": slot_id(d, t), "date": d, "startTime": t,
     "endTime": f"{int(t[:2]) + 1:02d}:00", "status": "SELECTED"}
    for d, t in slots]}] if slots else []
  return {"screen": "REWARD_HOURS", "components": [{
    "type": "BOOKED_HOURS_LIST",
    "props": {"items": items, "bonusHours": 4, "bonusHoursRemaining": remaining,
              "challengeHours": 0, "challengeHoursRemaining": 0,
              "totalRemainingHours": remaining},
  }]}


# ── the days on offer ────────────────────────────────────────────────────────

def test_the_offered_days_are_flattened_across_the_month_boundary():
  """October's window offers 1 November, so grouping by month would mislead."""
  days = parse_bookable_days(SELECT_DAYS)

  assert [d["date"] for d in days] == ["2026-10-10", "2026-10-11", "2026-10-17", "2026-11-01"]
  assert days[2]["available"] is False


def test_the_booking_window_is_the_first_offered_month_not_the_hour_s_month():
  """The capture put 1 November slots on the 2026-10 path and they stuck."""
  assert booking_window(parse_bookable_days(SELECT_DAYS)) == "2026-10"


def test_no_days_on_offer_has_no_window():
  assert booking_window([]) is None
  assert booking_window(None) is None


@pytest.mark.parametrize("payload", [None, {}, {"components": []}, "html"])
def test_an_unreadable_days_screen_is_none(payload):
  assert parse_bookable_days(payload) is None


# ── a day's slots ────────────────────────────────────────────────────────────

def test_a_day_s_slots_report_what_is_free_and_what_is_already_taken():
  slots = parse_day_slots(day_slots("2026-10-10", selected=("09:00",)))

  assert len(slots) == 15
  assert slots[0]["start_time"] == "00:00" and slots[-1]["start_time"] == "14:00"
  nine = next(s for s in slots if s["start_time"] == "09:00")
  assert nine["selected"] is True
  assert nine["available"] is True          # already ours, so still selectable


def test_a_non_bookable_day_is_an_empty_list_not_a_failure():
  assert parse_day_slots({"slots": []}) == []


def test_slot_ids_match_edf_s_own_format():
  assert slot_id("2026-10-10", "09:00") == "SLOT-2026-10-10-09-10"
  assert slot_id("2026-11-01", "00:00") == "SLOT-2026-11-01-00-01"


# ── the request body ─────────────────────────────────────────────────────────

def test_the_body_labels_local_time_as_z_exactly_as_the_app_does():
  """EDF reads the Z as local. Sending a true UTC instant books the wrong hour."""
  body = booking_payload([("2026-10-10", "09:00")])

  assert body == {"timeslots": [{
    "id": "SLOT-2026-10-10-09-10",
    "startDateTime": "2026-10-10T09:00:00.000Z",
    "endDateTime": "2026-10-10T10:00:00.000Z",
  }]}


def test_an_empty_set_is_the_cancel_everything_body():
  assert booking_payload([]) == {"timeslots": []}


def test_hours_are_sorted_and_deduplicated():
  body = booking_payload([("2026-10-11", "10:00"), ("2026-10-10", "09:00"), ("2026-10-11", "10:00")])

  assert [t["id"] for t in body["timeslots"]] == ["SLOT-2026-10-10-09-10", "SLOT-2026-10-11-10-11"]


def test_the_response_is_read_back_for_what_was_actually_stored():
  result = parse_booking_result({
    "postedTimeslots": [{"id": "SLOT-2026-10-10-09-10", "status": "SELECTED"}],
    "hoursBooked": 1, "remainingHours": 3,
  })

  assert result == {"hours_booked": 1, "remaining_hours": 3, "slot_ids": ["SLOT-2026-10-10-09-10"]}


# ── hour parsing and set arithmetic ──────────────────────────────────────────

@pytest.mark.parametrize("value,expected", [
  ("2026-10-10 09:00", ("2026-10-10", "09:00")),
  ("2026-10-10T09:00", ("2026-10-10", "09:00")),
  ("2026-10-10T09:00:00", ("2026-10-10", "09:00")),
  ("2026-10-10 09:30", ("2026-10-10", "09:00")),      # whole hours only
  (("2026-10-10", "09:00"), ("2026-10-10", "09:00")),
])
def test_hours_are_accepted_in_the_shapes_an_automation_would_write(value, expected):
  assert normalise_hour(value) == expected


@pytest.mark.parametrize("value", ["2026-10-10", "not a date 09:00", "2026-13-40 09:00", ""])
def test_a_nonsense_hour_is_rejected_rather_than_booked(value):
  with pytest.raises(ValueError):
    normalise_hour(value)


def test_add_keeps_what_is_already_booked():
  assert apply_mode([("2026-10-10", "09:00")], [("2026-10-10", "10:00")], "add") == [
    ("2026-10-10", "09:00"), ("2026-10-10", "10:00")]


def test_replace_cancels_everything_not_named():
  assert apply_mode([("2026-10-10", "09:00")], [("2026-10-11", "09:00")], "replace") == [
    ("2026-10-11", "09:00")]


def test_remove_gives_back_only_what_is_named():
  assert apply_mode(
    [("2026-10-10", "09:00"), ("2026-10-10", "10:00")], [("2026-10-10", "09:00")], "remove"
  ) == [("2026-10-10", "10:00")]


def test_adding_an_hour_already_booked_is_not_a_double_booking():
  assert apply_mode([("2026-10-10", "09:00")], [("2026-10-10", "09:00")], "add") == [
    ("2026-10-10", "09:00")]


def test_an_unknown_mode_is_refused():
  with pytest.raises(ValueError):
    apply_mode([], [], "wipe")


# ── booking end to end ───────────────────────────────────────────────────────

class FakeClient:
  def __init__(self, booked=(), remaining=4, days=SELECT_DAYS):
    self._booked = list(booked)
    self._remaining = remaining
    self._days = days
    self.puts = []
    self.hours_reads = 0

  async def async_get_flextras_booked_hours(self, account_id, property_id):
    self.hours_reads += 1
    return hours_screen(self._booked, self._remaining)

  async def async_get_flextras_bookable_days(self, account_id, property_id):
    return self._days

  async def async_put_flextras_bookings(self, account_id, property_id, window, payload):
    self.puts.append((window, payload))
    booked = len(payload["timeslots"])
    return {"postedTimeslots": payload["timeslots"], "hoursBooked": booked,
            "remainingHours": self._remaining + len(self._booked) - booked}


class FakeHass:
  def __init__(self, client):
    self.data = {DOMAIN: {ACCOUNT_ID: {
      DATA_CLIENT: client,
      "ACCOUNT": type("R", (), {"account": {"property_ids": [PROPERTY_ID]}})(),
      DATA_FLEXTRAS_HOURS.format(ACCOUNT_ID): None,
    }}}


@pytest.mark.asyncio
async def test_booking_an_hour_sends_the_full_set_not_just_the_new_hour():
  client = FakeClient(booked=[("2026-10-10", "09:00")], remaining=3)
  hass = FakeHass(client)

  await async_book_flextras_hours(hass, ACCOUNT_ID, ["2026-10-10 10:00"], "add")

  window, payload = client.puts[0]
  assert window == "2026-10"
  assert [t["id"] for t in payload["timeslots"]] == [
    "SLOT-2026-10-10-09-10", "SLOT-2026-10-10-10-11"]


@pytest.mark.asyncio
async def test_the_booked_set_is_re_read_rather_than_taken_from_the_cache():
  """A cached copy can be half an hour old; sending it would cancel newer hours."""
  client = FakeClient(booked=[("2026-10-10", "09:00")], remaining=3)
  hass = FakeHass(client)

  await async_book_flextras_hours(hass, ACCOUNT_ID, ["2026-10-10 10:00"], "add")

  assert client.hours_reads == 1


@pytest.mark.asyncio
async def test_cancelling_everything_sends_the_empty_array():
  client = FakeClient(booked=[("2026-10-10", "09:00")], remaining=3)

  await async_book_flextras_hours(FakeHass(client), ACCOUNT_ID, [], "replace")

  assert client.puts[0][1] == {"timeslots": []}


@pytest.mark.asyncio
async def test_hours_can_be_booked_on_the_day_that_spills_into_the_next_month():
  client = FakeClient()

  await async_book_flextras_hours(FakeHass(client), ACCOUNT_ID, ["2026-11-01 00:00"], "add")

  window, payload = client.puts[0]
  assert window == "2026-10"                      # the window, not the hour's month
  assert payload["timeslots"][0]["id"] == "SLOT-2026-11-01-00-01"


@pytest.mark.asyncio
async def test_a_day_edf_is_not_offering_is_refused_before_any_write():
  client = FakeClient()

  with pytest.raises(ValueError, match="not a day EDF is offering"):
    await async_book_flextras_hours(FakeHass(client), ACCOUNT_ID, ["2026-10-17 09:00"], "add")

  assert client.puts == []


@pytest.mark.asyncio
async def test_spending_more_hours_than_are_left_is_refused_before_any_write():
  client = FakeClient(booked=[], remaining=2)

  with pytest.raises(ValueError, match="only 2 are left"):
    await async_book_flextras_hours(
      FakeHass(client), ACCOUNT_ID,
      ["2026-10-10 09:00", "2026-10-10 10:00", "2026-10-10 11:00"], "add")

  assert client.puts == []


@pytest.mark.asyncio
async def test_moving_hours_within_the_allowance_is_allowed():
  """Replacing two booked hours with two others spends nothing extra."""
  client = FakeClient(booked=[("2026-10-10", "09:00"), ("2026-10-10", "10:00")], remaining=0)

  await async_book_flextras_hours(
    FakeHass(client), ACCOUNT_ID, ["2026-10-11 09:00", "2026-10-11 10:00"], "replace")

  assert [t["id"] for t in client.puts[0][1]["timeslots"]] == [
    "SLOT-2026-10-11-09-10", "SLOT-2026-10-11-10-11"]


@pytest.mark.asyncio
async def test_an_unreadable_current_booking_stops_the_write():
  """Guessing the current set here would cancel whatever could not be read."""
  client = FakeClient()
  client.async_get_flextras_booked_hours = lambda a, p: _none()

  with pytest.raises(ValueError, match="Could not read the hours currently booked"):
    await async_book_flextras_hours(FakeHass(client), ACCOUNT_ID, ["2026-10-10 09:00"], "add")

  assert client.puts == []


async def _none():
  return None


@pytest.mark.asyncio
async def test_nothing_on_offer_stops_the_write():
  client = FakeClient(days={"components": []})

  with pytest.raises(ValueError, match="not offering any days"):
    await async_book_flextras_hours(FakeHass(client), ACCOUNT_ID, ["2026-10-10 09:00"], "add")

  assert client.puts == []


# The body the EDF app itself sent on 5 October 2026, copied verbatim from the capture.
# Reproducing it exactly is the whole basis for trusting the write path.
APP_BODY = {"timeslots": [
  {"id": "SLOT-2026-10-11-09-10",
   "startDateTime": "2026-10-11T09:00:00.000Z", "endDateTime": "2026-10-11T10:00:00.000Z"},
  {"id": "SLOT-2026-10-11-10-11",
   "startDateTime": "2026-10-11T10:00:00.000Z", "endDateTime": "2026-10-11T11:00:00.000Z"},
  {"id": "SLOT-2026-10-11-11-12",
   "startDateTime": "2026-10-11T11:00:00.000Z", "endDateTime": "2026-10-11T12:00:00.000Z"},
  {"id": "SLOT-2026-10-11-12-13",
   "startDateTime": "2026-10-11T12:00:00.000Z", "endDateTime": "2026-10-11T13:00:00.000Z"},
]}


def test_the_body_matches_what_the_edf_app_sent_byte_for_byte():
  assert booking_payload([("2026-10-11", f"{h:02d}:00") for h in (9, 10, 11, 12)]) == APP_BODY
