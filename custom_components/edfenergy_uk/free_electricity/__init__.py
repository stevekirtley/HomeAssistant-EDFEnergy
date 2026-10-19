from datetime import datetime

from ..api_client.free_electricity_sessions import FreeElectricitySession


def current_free_electricity_session_event(current_date: datetime, events: list[FreeElectricitySession]) -> FreeElectricitySession | None:
  if events is not None:
    for event in events:
      if event.start <= current_date and event.end >= current_date:
        return event
  return None


def get_next_free_electricity_session_event(current_date: datetime, events: list[FreeElectricitySession]) -> FreeElectricitySession | None:
  next_event = None
  if events is not None:
    for event in events:
      if event.start > current_date and (next_event is None or event.start < next_event.start):
        next_event = event
  return next_event


def current_or_next_free_electricity_session_event(current_date: datetime, events: list[FreeElectricitySession]) -> FreeElectricitySession | None:
  """The session in progress, or failing that the next one to start.

  This is what an automation planning around a free window wants: while a window is open it
  is the window, and otherwise it is the one to prepare for.
  """
  current = current_free_electricity_session_event(current_date, events)
  if current is not None:
    return current
  return get_next_free_electricity_session_event(current_date, events)
