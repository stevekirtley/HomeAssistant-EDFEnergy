"""Coordinator for the free hours a customer has booked through Flextras.

Flextras hands out free electricity hours - a joining bonus, and more for meeting the
monthly challenge - and lets the customer spend them on whichever weekend hours they
choose, an hour at a time. Those hours are free electricity like any other, so they are
published through the same free electricity sessions feed as Power Perks and Sunday
Saver, and reach the calendar, the sensors and any automation built on them.

Unlike the other sources, this one changes at the customer's whim: hours can be moved or
given back right up to the Thursday before. The sessions coordinator therefore retracts
any booking that disappears before it starts, so the calendar follows the app rather than
keeping a window the customer has cancelled.
"""
import logging
from datetime import datetime, timedelta

from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util.dt import utcnow

from ..api_client import EDFEnergyApiClient
from ..api_client.flextras_hours import (
  UK_TZ,
  booking_payload,
  booking_window,
  parse_bookable_days,
  parse_booked_hours,
  parse_booking_result,
  parse_day_slots,
  parse_entitlements,
)
from ..api_client.free_electricity_sessions import FreeElectricitySession
from ..const import (
  COORDINATOR_REFRESH_IN_SECONDS,
  DATA_CLIENT,
  DATA_FLEXTRAS_HOURS,
  DATA_FLEXTRAS_HOURS_COORDINATOR,
  DOMAIN,
  REFRESH_RATE_IN_MINUTES_FLEXTRAS_HOURS,
)
from . import BaseCoordinatorResult
from .flextras import get_property_id

_LOGGER = logging.getLogger(__name__)

SOURCE = "flextras_hours"


def session_code(start: datetime) -> str:
  """The code for a booked window, keyed on when it starts in local time."""
  return f"{SOURCE}_{start.astimezone(UK_TZ).strftime('%Y%m%d%H%M')}"


def windows_to_sessions(windows) -> list[FreeElectricitySession]:
  return sorted(
    (FreeElectricitySession(session_code(start), start, end, SOURCE) for start, end in windows),
    key=lambda s: s.start,
  )


class FlextrasHoursCoordinatorResult(BaseCoordinatorResult):
  """The customer's booked hours, plus how many they have left to spend."""

  sessions: list[FreeElectricitySession]
  available: bool
  bonus_hours: float | None
  bonus_hours_remaining: float | None
  challenge_hours: float | None
  challenge_hours_remaining: float | None
  total_remaining_hours: float | None
  hours: list[tuple[str, str]]
  bookable_days: list[dict]
  entitlements: list[dict]

  def __init__(
    self,
    last_evaluated: datetime,
    request_attempts: int,
    sessions: list[FreeElectricitySession],
    available: bool = True,
    bonus_hours: float | None = None,
    bonus_hours_remaining: float | None = None,
    challenge_hours: float | None = None,
    challenge_hours_remaining: float | None = None,
    total_remaining_hours: float | None = None,
    hours: list[tuple[str, str]] | None = None,
    bookable_days: list[dict] | None = None,
    entitlements: list[dict] | None = None,
    last_error=None,
  ):
    super().__init__(last_evaluated, request_attempts, REFRESH_RATE_IN_MINUTES_FLEXTRAS_HOURS, None, last_error)
    self.sessions = sessions
    self.available = available
    self.bonus_hours = bonus_hours
    self.bonus_hours_remaining = bonus_hours_remaining
    self.challenge_hours = challenge_hours
    self.challenge_hours_remaining = challenge_hours_remaining
    self.total_remaining_hours = total_remaining_hours
    self.hours = hours or []
    self.bookable_days = bookable_days or []
    self.entitlements = entitlements or []


async def async_refresh_flextras_hours(
  current: datetime,
  fetch_hours,
  existing_result: FlextrasHoursCoordinatorResult | None,
  fetch_bookable_days=None,
) -> FlextrasHoursCoordinatorResult:
  if existing_result is not None and current < existing_result.next_refresh:
    return existing_result

  payload = await fetch_hours()
  parsed = parse_booked_hours(payload)

  if parsed is None:
    # Could not read the screen. Keep whatever was booked last time: an unreadable
    # response must never be mistaken for the customer cancelling.
    previous = existing_result.sessions if existing_result is not None else []
    attempts = existing_result.request_attempts + 1 if existing_result is not None else 1
    # Warn on the way into the failure only. If EDF break the screen this runs every few
    # minutes, and a warning per retry is how a log fills up with one fault.
    if payload is not None and (existing_result is None or existing_result.available):
      _LOGGER.warning("Flextras hours screen was not recognised; keeping the hours already booked")
    elif payload is not None:
      _LOGGER.debug("Flextras hours screen still not recognised (attempt %d)", attempts)
    return FlextrasHoursCoordinatorResult(
      current - timedelta(minutes=REFRESH_RATE_IN_MINUTES_FLEXTRAS_HOURS)
      + timedelta(minutes=min(5 * attempts, REFRESH_RATE_IN_MINUTES_FLEXTRAS_HOURS)),
      attempts,
      previous,
      available=False,
      bonus_hours=existing_result.bonus_hours if existing_result is not None else None,
      bonus_hours_remaining=existing_result.bonus_hours_remaining if existing_result is not None else None,
      challenge_hours=existing_result.challenge_hours if existing_result is not None else None,
      challenge_hours_remaining=existing_result.challenge_hours_remaining if existing_result is not None else None,
      total_remaining_hours=existing_result.total_remaining_hours if existing_result is not None else None,
      hours=existing_result.hours if existing_result is not None else None,
      bookable_days=existing_result.bookable_days if existing_result is not None else None,
      entitlements=existing_result.entitlements if existing_result is not None else None,
      last_error=Exception("Flextras hours unavailable"),
    )

  sessions = windows_to_sessions(parsed["windows"])

  # The days on offer are only needed to book, so a failure to read them must not take
  # the booked hours down with it.
  bookable_days = existing_result.bookable_days if existing_result is not None else []
  if fetch_bookable_days is not None:
    days = parse_bookable_days(await fetch_bookable_days())
    if days is not None:
      bookable_days = days

  _LOGGER.debug("Flextras hours: %d booked window(s), %s hour(s) left to spend, %d day(s) on offer",
                len(sessions), parsed.get("total_remaining_hours"), len(bookable_days))
  return FlextrasHoursCoordinatorResult(
    current, 1, sessions, True,
    parsed.get("bonus_hours"),
    parsed.get("bonus_hours_remaining"),
    parsed.get("challenge_hours"),
    parsed.get("challenge_hours_remaining"),
    parsed.get("total_remaining_hours"),
    parsed.get("hours"),
    bookable_days,
    parse_entitlements(payload),
  )


async def async_setup_flextras_hours_coordinator(hass, account_id: str, entry):
  key = DATA_FLEXTRAS_HOURS.format(account_id)
  coordinator_key = DATA_FLEXTRAS_HOURS_COORDINATOR.format(account_id)

  async def async_fetch():
    # Looked up per refresh, not once at setup: the account coordinator may not have
    # answered yet when we are wired up, and a property id of None then sticks forever.
    property_id = get_property_id(hass, account_id)
    if property_id is None:
      return None
    client: EDFEnergyApiClient = hass.data[DOMAIN][account_id][DATA_CLIENT]
    return await client.async_get_flextras_booked_hours(account_id, property_id)

  async def async_fetch_days():
    property_id = get_property_id(hass, account_id)
    if property_id is None:
      return None
    client: EDFEnergyApiClient = hass.data[DOMAIN][account_id][DATA_CLIENT]
    return await client.async_get_flextras_bookable_days(account_id, property_id)

  async def async_update():
    current = utcnow()
    existing = hass.data[DOMAIN][account_id].get(key)
    result = await async_refresh_flextras_hours(current, async_fetch, existing, async_fetch_days)
    hass.data[DOMAIN][account_id][key] = result
    return result

  hass.data[DOMAIN][account_id][coordinator_key] = DataUpdateCoordinator(
    hass,
    _LOGGER,
    name=f"flextras_hours_{account_id}",
    update_method=async_update,
    update_interval=timedelta(seconds=COORDINATOR_REFRESH_IN_SECONDS),
    always_update=True,
  )

  # An account that is not on Flextras, or has no property, must not stop setup.
  await hass.data[DOMAIN][account_id][coordinator_key].async_refresh()


def normalise_hour(value) -> tuple[str, str]:
  """Accept an hour as "YYYY-MM-DD HH:MM", an ISO timestamp or a (date, time) pair.

  Returned as (date, "HH:00") in local time. Hours are whole, so any minutes are
  discarded rather than quietly booking something EDF cannot store.
  """
  if isinstance(value, (list, tuple)) and len(value) == 2:
    date_str, time_str = str(value[0]), str(value[1])
  else:
    text = str(value).strip().replace("T", " ")
    if " " not in text:
      raise ValueError(f"'{value}' is not a date and time")
    date_str, time_str = text.split(" ", 1)
  try:
    hour = int(time_str.strip()[:2])
  except ValueError as err:
    raise ValueError(f"'{value}' has no readable hour") from err
  datetime.strptime(date_str, "%Y-%m-%d")      # raises if the date is not a date
  if not 0 <= hour <= 23:
    raise ValueError(f"'{value}' is not an hour of the day")
  return date_str, f"{hour:02d}:00"


def apply_mode(booked: list[tuple[str, str]], hours: list[tuple[str, str]], mode: str):
  """The complete set of hours to send, given what is booked and what was asked for."""
  if mode == "replace":
    return sorted(set(hours))
  if mode == "remove":
    return sorted(set(booked) - set(hours))
  if mode == "add":
    return sorted(set(booked) | set(hours))
  raise ValueError(f"Unknown mode '{mode}'")


async def async_book_flextras_hours(hass, account_id: str, hours, mode: str = "add"):
  """Book, move or cancel free hours, then refresh so the calendar follows immediately.

  EDF's booking call replaces the whole set, so the set is rebuilt here from a fresh read
  of what is currently booked rather than from the coordinator's cached copy. A cached
  copy up to thirty minutes old could be missing hours booked in the app in the meantime,
  and sending it would cancel them.
  """
  from ..api_client import EDFEnergyApiClient
  from .flextras import get_property_id

  property_id = get_property_id(hass, account_id)
  if property_id is None:
    raise ValueError(f"No property found for account {account_id}")

  client: EDFEnergyApiClient = hass.data[DOMAIN][account_id][DATA_CLIENT]
  wanted = [normalise_hour(h) for h in (hours or [])]

  current_screen = parse_booked_hours(await client.async_get_flextras_booked_hours(account_id, property_id))
  if current_screen is None:
    raise ValueError("Could not read the hours currently booked, so nothing was changed")

  days = parse_bookable_days(await client.async_get_flextras_bookable_days(account_id, property_id))
  window = booking_window(days)
  if window is None:
    raise ValueError("EDF is not offering any days to book at the moment")

  offered = {d["date"] for d in days if d["available"]}
  for date_str, start_time in wanted:
    if mode != "remove" and date_str not in offered:
      raise ValueError(f"{date_str} is not a day EDF is offering; bookable days are {sorted(offered)}")

  desired = apply_mode(current_screen["hours"], wanted, mode)
  remaining = current_screen.get("total_remaining_hours")
  spending = len(desired) - len(current_screen["hours"])
  if remaining is not None and spending > remaining:
    raise ValueError(
      f"That needs {spending} more hour(s) but only {remaining:g} are left to spend"
    )

  _LOGGER.debug("Flextras booking for %s window %s: %s -> %s",
                account_id, window, current_screen["hours"], desired)
  result = parse_booking_result(
    await client.async_put_flextras_bookings(account_id, property_id, window, booking_payload(desired))
  )

  coordinator = hass.data[DOMAIN][account_id].get(DATA_FLEXTRAS_HOURS_COORDINATOR.format(account_id))
  if coordinator is not None:
    # Clear the result so the refresh actually re-fetches rather than waiting out the
    # thirty minute interval, then let the sessions coordinator pick the change up.
    hass.data[DOMAIN][account_id][DATA_FLEXTRAS_HOURS.format(account_id)] = None
    await coordinator.async_refresh()

  return result or {}


async def async_get_flextras_day_slots(hass, account_id: str, date: str):
  """The hourly slots for one day, for the panel's booking grid."""
  from ..api_client import EDFEnergyApiClient
  from .flextras import get_property_id

  property_id = get_property_id(hass, account_id)
  if property_id is None:
    return []
  client: EDFEnergyApiClient = hass.data[DOMAIN][account_id][DATA_CLIENT]
  return parse_day_slots(await client.async_get_flextras_day_slots(account_id, property_id, date)) or []
