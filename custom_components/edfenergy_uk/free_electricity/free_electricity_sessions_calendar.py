from datetime import datetime
import logging

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import generate_entity_id
from homeassistant.util.dt import utcnow
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.helpers.restore_state import RestoreEntity

from . import current_free_electricity_session_event, get_next_free_electricity_session_event
from ..coordinators.free_electricity_sessions import FreeElectricitySessionsCoordinatorResult
from .base import EDFEnergyFreeElectricitySensor

_LOGGER = logging.getLogger(__name__)


class EDFEnergyFreeElectricitySessionsCalendar(EDFEnergyFreeElectricitySensor, CoordinatorEntity, CalendarEntity, RestoreEntity):
  """Calendar for free electricity sessions — current/next/ranged, mirroring the Octopus calendar."""

  _unrecorded_attributes = frozenset({"data_last_retrieved"})

  def __init__(self, hass: HomeAssistant, coordinator, account_id: str):
    CoordinatorEntity.__init__(self, coordinator)
    EDFEnergyFreeElectricitySensor.__init__(self, account_id)
    self._account_id = account_id
    self._event = None
    self._events = []
    self.entity_id = generate_entity_id("calendar.{}", self.unique_id, hass=hass)

  @property
  def unique_id(self):
    return f"edf_energy_{self._account_id}_free_electricity_session"

  @property
  def name(self):
    return f"Free Electricity ({self._account_id})"

  @property
  def event(self) -> CalendarEvent | None:
    return self._event

  @callback
  def _handle_coordinator_update(self) -> None:
    result: FreeElectricitySessionsCoordinatorResult = self.coordinator.data if self.coordinator is not None else None
    self._events = result.events if result is not None else []

    current_date = utcnow()
    current_event = current_free_electricity_session_event(current_date, self._events)
    if current_event is not None:
      self._event = CalendarEvent(uid=current_event.code, summary="EDF Energy Free Electricity", start=current_event.start, end=current_event.end)
    else:
      next_event = get_next_free_electricity_session_event(current_date, self._events)
      self._event = CalendarEvent(uid=next_event.code, summary="EDF Energy Free Electricity", start=next_event.start, end=next_event.end) if next_event else None

    super()._handle_coordinator_update()

  async def async_get_events(self, hass, start_date: datetime, end_date: datetime) -> list[CalendarEvent]:
    return [
      CalendarEvent(uid=e.code, summary="EDF Energy Free Electricity", start=e.start, end=e.end)
      for e in (self._events or [])
      if e.start < end_date and e.end > start_date
    ]
