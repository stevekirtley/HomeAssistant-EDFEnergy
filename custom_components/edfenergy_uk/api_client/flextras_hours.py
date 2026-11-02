"""The free hours a customer has booked through Flextras.

Flextras lets you spend your earned hours on whichever weekend hours you like, an hour at
a time, and change the choice up to the Thursday before. EDF serve the result as a
server-driven UI screen rather than a plain API, but the screen carries a machine-readable
list of the chosen slots alongside the text meant for the app, and that is what is read
here.

The times in that list are local, despite the booking call labelling them as UTC. EDF's
own response proves it: the app books an 09:00 slot as "09:00:00.000Z" and the server
echoes it back as "08:00:00.000Z", which is the correct UTC for 09:00 BST. So the date and
time are read as Europe/London. That matters beyond pedantry, because hours can be booked
either side of a clock change.
"""
import re
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from homeassistant.util.dt import as_utc

UK_TZ = ZoneInfo("Europe/London")

BOOKED_HOURS_LIST = "BOOKED_HOURS_LIST"


def _slot_datetime(date_str, time_str) -> datetime | None:
  """A slot's date and wall-clock time as a UTC instant."""
  if not isinstance(date_str, str) or not isinstance(time_str, str):
    return None
  try:
    naive = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
  except ValueError:
    return None
  return as_utc(naive.replace(tzinfo=UK_TZ))


def _merge_adjacent(windows: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
  """Join hours that run back to back into one window.

  Hours are booked one at a time, so four consecutive ones arrive as four slots. As a
  single window they read better on a calendar and behave better for anything deciding
  whether it is in a free period. Hours that are not adjacent stay separate, which they
  may well be - the booking screen allows gaps.
  """
  merged: list[tuple[datetime, datetime]] = []
  for start, end in sorted(windows):
    if merged and start <= merged[-1][1]:
      if end > merged[-1][1]:
        merged[-1] = (merged[-1][0], end)
    else:
      merged.append((start, end))
  return merged


def parse_booked_hours(response_body) -> dict | None:
  """Pull the booked hours and the hour balances out of the Flextras hours screen.

  Returns {"windows": [(start, end), ...], "hours": [(date, start_time), ...],
  "bonus_hours", "bonus_hours_remaining",
  "challenge_hours", "challenge_hours_remaining", "total_remaining_hours"}, or None if the
  payload is not that screen at all - which the caller treats as "ask again later" rather
  than "nothing is booked", so a bad response never silently cancels a booking.
  """
  if not isinstance(response_body, dict):
    return None
  components = response_body.get("components")
  if not isinstance(components, list):
    return None

  booked = next(
    (c for c in components
     if isinstance(c, dict) and c.get("type") == BOOKED_HOURS_LIST and isinstance(c.get("props"), dict)),
    None,
  )
  if booked is None:
    return None

  props = booked["props"]
  windows: list[tuple[datetime, datetime]] = []
  hours: list[tuple[str, str]] = []
  for item in props.get("items") or []:
    if not isinstance(item, dict):
      continue
    for slot in item.get("rawTimeSlots") or []:
      if not isinstance(slot, dict):
        continue
      start = _slot_datetime(slot.get("date"), slot.get("startTime"))
      end = _slot_datetime(slot.get("date"), slot.get("endTime"))
      if start is None or end is None:
        continue
      if end <= start:
        # An hour that runs over midnight is dated by the day it starts.
        end = end + timedelta(days=1)
      windows.append((start, end))
      # Kept unmerged as well: a booking has to be re-sent as a complete set of whole
      # hours, and rebuilding those from the merged windows would be a needless round trip
      # through local time.
      hours.append((slot["date"], slot["startTime"]))

  def _as_number(key):
    value = props.get(key)
    return value if isinstance(value, (int, float)) else None

  return {
    "windows": _merge_adjacent(windows),
    "hours": sorted(set(hours)),
    "bonus_hours": _as_number("bonusHours"),
    "bonus_hours_remaining": _as_number("bonusHoursRemaining"),
    "challenge_hours": _as_number("challengeHours"),
    "challenge_hours_remaining": _as_number("challengeHoursRemaining"),
    "total_remaining_hours": _as_number("totalRemainingHours"),
  }


SELECT_DAYS_LIST = "SELECT_DAYS_LIST"
HOURS_TO_USE_LIST = "HOURS_TO_USE_LIST"

# The per-bucket hour count is only given in prose ("You have 4 hours left to use"); the
# screen has no numeric field for it. The aggregate is machine-readable, so this is a
# best effort used for the breakdown only, never for deciding what can be booked.
_HOURS_IN_TEXT = re.compile(r"(\d+(?:\.\d+)?)\s*hour")


def slot_id(date_str: str, start_time: str) -> str:
  """EDF's id for an hourly slot, e.g. SLOT-2026-10-10-09-10.

  Derived rather than round-tripped, so a booking can be made without first asking for
  the day's slots. Hours are always whole, and the offered slots run 00:00 to 15:00, so
  the end hour never wraps past midnight.
  """
  hour = int(start_time[:2])
  return f"SLOT-{date_str}-{hour:02d}-{hour + 1:02d}"


def parse_bookable_days(response_body) -> list[dict] | None:
  """The days EDF is currently offering, from the book-hours screen.

  Returned flat and in date order. The screen groups them by month, but the window spills
  across the boundary - October's offered Sunday 1 November - so the grouping is not a
  distinction the caller should have to care about.
  """
  if not isinstance(response_body, dict):
    return None
  components = response_body.get("components")
  if not isinstance(components, list):
    return None

  block = next(
    (c for c in components
     if isinstance(c, dict) and c.get("type") == SELECT_DAYS_LIST and isinstance(c.get("props"), dict)),
    None,
  )
  if block is None:
    return None

  days: list[dict] = []
  for month in block["props"].get("months") or []:
    if not isinstance(month, dict):
      continue
    for day in month.get("days") or []:
      if not isinstance(day, dict) or not isinstance(day.get("date"), str):
        continue
      days.append({
        "date": day["date"],
        "day": day.get("day"),
        "available": bool(day.get("isAvailable")),
      })
  return sorted(days, key=lambda d: d["date"])


def booking_window(bookable_days: list[dict] | None) -> str | None:
  """The YYYY-MM the booking PUT is addressed to.

  It is the month of the first day on offer, not the month of the hours being booked:
  the capture shows 1 November slots accepted on the 2026-10 path. The month scopes the
  booking window, not the slots within it.
  """
  if not bookable_days:
    return None
  return bookable_days[0]["date"][:7]


def parse_day_slots(response_body) -> list[dict] | None:
  """The hourly slots for one day, with whether each is free to take.

  A day that cannot be booked comes back with an empty slots list, which is a real
  answer and so returned as an empty list rather than None.
  """
  if not isinstance(response_body, dict):
    return None
  slots = response_body.get("slots")
  if not isinstance(slots, list):
    return None

  parsed = []
  for slot in slots:
    if not isinstance(slot, dict):
      continue
    start = _slot_datetime(slot.get("date"), slot.get("startTime"))
    if start is None or not isinstance(slot.get("endTime"), str):
      continue
    status = slot.get("status")
    parsed.append({
      "slot_id": slot.get("slotId") or slot_id(slot["date"], slot["startTime"]),
      "date": slot["date"],
      "start_time": slot["startTime"],
      "end_time": slot["endTime"],
      "status": status,
      "selected": status == "SELECTED",
      "available": status in ("AVAILABLE", "SELECTED"),
      "start": start,
    })
  return sorted(parsed, key=lambda s: (s["date"], s["start_time"]))


def booking_payload(hours: list[tuple[str, str]]) -> dict:
  """The PUT body for a complete set of booked hours.

  Each hour is a (date, start_time) pair in local time. The timestamps carry a "Z" that
  EDF's own app also sends and the server reads as local - it echoes 09:00:00.000Z back
  as 08:00:00.000Z for a BST date. Sending a genuine UTC instant would therefore book the
  wrong hour, so the app's convention is followed deliberately.
  """
  timeslots = []
  for date_str, start_time in sorted(set(hours)):
    end_hour = int(start_time[:2]) + 1
    timeslots.append({
      "id": slot_id(date_str, start_time),
      "startDateTime": f"{date_str}T{start_time}:00.000Z",
      "endDateTime": f"{date_str}T{end_hour:02d}:00:00.000Z",
    })
  return {"timeslots": timeslots}


def parse_booking_result(response_body) -> dict | None:
  """What EDF confirmed it stored, after a booking PUT."""
  if not isinstance(response_body, dict) or not isinstance(response_body.get("postedTimeslots"), list):
    return None
  return {
    "hours_booked": response_body.get("hoursBooked"),
    "remaining_hours": response_body.get("remainingHours"),
    "slot_ids": [s.get("id") for s in response_body["postedTimeslots"] if isinstance(s, dict)],
  }


def parse_entitlements(response_body) -> list[dict] | None:
  """The hour entitlements and when each expires, from the hours screen.

  Separate buckets with separate expiry dates - a joining bonus, and challenge hours
  earned month by month - which the aggregate counters flatten away. Worth having
  because unused challenge hours do not simply lapse: EDF books them for you at a time
  of their choosing, so knowing an expiry is coming is what lets you pick the slot first.
  """
  if not isinstance(response_body, dict):
    return None
  components = response_body.get("components")
  if not isinstance(components, list):
    return None

  block = next(
    (c for c in components
     if isinstance(c, dict) and c.get("type") == HOURS_TO_USE_LIST and isinstance(c.get("props"), dict)),
    None,
  )
  if block is None:
    return None

  entitlements = []
  for item in block["props"].get("items") or []:
    if not isinstance(item, dict):
      continue
    description = item.get("description") or ""
    match = _HOURS_IN_TEXT.search(description)
    expires = item.get("date")
    entitlements.append({
      "kind": item.get("type"),
      "title": item.get("title"),
      "hours_left": float(match.group(1)) if match else None,
      "expires": expires if isinstance(expires, str) else None,
      "description": description,
    })
  return entitlements


# Fields on the hours screen that identify the customer rather than describe the hours.
# The entitlement id is base64 of "AccNo#<account>#PropId#<property>_Hours#<bucket>", so
# it goes nowhere near a diagnostics download.
_IDENTIFYING_FIELDS = ("id", "accountNumber", "propertyId")


def redact_hours_screen(response_body) -> dict | None:
  """The hours screen's shape, safe to attach to a bug report.

  Only part of this scheme can be exercised on any one account: a customer on a
  time-of-use tariff cannot join Weekend Saver, so they never earn challenge hours, and
  the challenge side of the screen is unobservable to them no matter how much they poke
  at it. Carrying the structure into diagnostics means an issue from someone it does
  apply to arrives with the payload already attached, rather than costing a round trip
  to ask for it.
  """
  if not isinstance(response_body, dict):
    return None
  summary = {"screen": response_body.get("screen"), "components": []}
  for component in response_body.get("components") or []:
    if not isinstance(component, dict):
      continue
    props = component.get("props") if isinstance(component.get("props"), dict) else {}
    entry = {"type": component.get("type"), "keys": sorted(props.keys())}
    # The counters and the entitlement breakdown are what a parser fix needs; the prose
    # and the booked slots are either noise or the customer's own routine.
    if component.get("type") == HOURS_TO_USE_LIST:
      entry["items"] = [
        {k: v for k, v in item.items() if k not in _IDENTIFYING_FIELDS}
        for item in props.get("items") or [] if isinstance(item, dict)
      ]
    elif component.get("type") == BOOKED_HOURS_LIST:
      entry["counters"] = {
        k: v for k, v in props.items() if isinstance(v, (int, float))
      }
      entry["booked_day_count"] = len(props.get("items") or [])
    summary["components"].append(entry)
  return summary
