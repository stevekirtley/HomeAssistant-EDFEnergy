import logging
from datetime import datetime

from homeassistant.core import HomeAssistant, callback
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.helpers.entity import generate_entity_id
from homeassistant.util.dt import now as ha_now, parse_datetime
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.event import (
  async_track_point_in_time,
  async_track_time_change,
  async_track_state_change_event,
)

from ..coordinators.sunday_saver import SundaySaverCoordinatorResult

_LOGGER = logging.getLogger(__name__)

_UNAVAILABLE_STATES = {STATE_UNAVAILABLE, STATE_UNKNOWN}


class EDFEnergySundaySaverFreeElectricity(CoordinatorEntity, BinarySensorEntity, RestoreEntity):
  """Binary sensor: on while within a Sunday Saver or event free electricity window.

  Sunday Saver takes precedence — if both windows overlap, Sunday Saver wins.
  State is driven by three mechanisms in order of precision:
    1. Exact point-in-time triggers at each window's start and end.
    2. A safeguard that re-evaluates at :01 and :31 every minute.
    3. An immediate evaluation on HA startup so a restart mid-window is handled.
  """

  def __init__(self, hass: HomeAssistant, coordinator, account_id: str):
    CoordinatorEntity.__init__(self, coordinator)
    self._account_id = account_id
    self._state = False
    self._cancel_start = None
    self._cancel_end = None
    self._cancel_event_start = None
    self._cancel_event_end = None
    self._cancel_safeguard = None
    self._cancel_event_sensor_tracking = None
    self.entity_id = generate_entity_id("binary_sensor.{}", self.unique_id, hass=hass)

  # ── Entity properties ──────────────────────────────────────────────────────

  @property
  def unique_id(self):
    return f"edf_energy_{self._account_id}_free_electricity_now"

  @property
  def name(self):
    return f"Free Electricity Now ({self._account_id})"

  @property
  def icon(self):
    return "mdi:lightning-bolt-circle"

  @property
  def is_on(self):
    return self._state

  # ── Evaluation helpers ─────────────────────────────────────────────────────

  def _sunday_saver_result(self) -> SundaySaverCoordinatorResult | None:
    return (
      self.coordinator.data
      if self.coordinator is not None and self.coordinator.data is not None
      else None
    )

  def _evaluate_sunday_saver(self, result: SundaySaverCoordinatorResult | None, current: datetime) -> bool:
    if result is None or not result.has_event:
      return False
    if result.start is None or result.end is None:
      return False
    return result.start <= current <= result.end

  def _get_event_window(self):
    """Return (start, end) datetimes from the event free sensors, or (None, None)."""
    start_id = f"sensor.edf_energy_{self._account_id}_event_free_start"
    end_id = f"sensor.edf_energy_{self._account_id}_event_free_end"
    start_state = self.hass.states.get(start_id)
    end_state = self.hass.states.get(end_id)
    if start_state is None or end_state is None:
      return None, None
    if start_state.state in _UNAVAILABLE_STATES or end_state.state in _UNAVAILABLE_STATES:
      return None, None
    try:
      start = parse_datetime(start_state.state)
      end = parse_datetime(end_state.state)
      return start, end
    except Exception:
      return None, None

  def _evaluate_event(self, current: datetime) -> bool:
    start, end = self._get_event_window()
    if start is None or end is None:
      return False
    return start <= current <= end

  def _evaluate(self, result: SundaySaverCoordinatorResult | None, current: datetime) -> bool:
    """Return True if within any free window. Sunday Saver takes precedence."""
    if self._evaluate_sunday_saver(result, current):
      return True
    return self._evaluate_event(current)

  # ── Trigger scheduling ─────────────────────────────────────────────────────

  def _schedule_sunday_saver_triggers(self, result: SundaySaverCoordinatorResult | None):
    if self._cancel_start:
      self._cancel_start()
      self._cancel_start = None
    if self._cancel_end:
      self._cancel_end()
      self._cancel_end = None

    if result is None or not result.has_event:
      return
    current = ha_now()

    if result.start is not None and result.start > current:
      @callback
      def _on_start(_now):
        _LOGGER.debug(f"Sunday Saver window started for account {self._account_id}")
        self._state = True
        self.async_write_ha_state()
      self._cancel_start = async_track_point_in_time(self.hass, _on_start, result.start)
      _LOGGER.debug(f"Scheduled Sunday Saver start trigger at {result.start} for account {self._account_id}")

    if result.end is not None and result.end > current:
      @callback
      def _on_end(_now):
        _LOGGER.debug(f"Sunday Saver window ended for account {self._account_id}")
        # Sunday Saver just ended — check whether an event window is still active
        self._state = self._evaluate_event(ha_now())
        self.async_write_ha_state()
      self._cancel_end = async_track_point_in_time(self.hass, _on_end, result.end)
      _LOGGER.debug(f"Scheduled Sunday Saver end trigger at {result.end} for account {self._account_id}")

  def _schedule_event_triggers(self):
    if self._cancel_event_start:
      self._cancel_event_start()
      self._cancel_event_start = None
    if self._cancel_event_end:
      self._cancel_event_end()
      self._cancel_event_end = None

    start, end = self._get_event_window()
    if start is None or end is None:
      return
    current = ha_now()

    if start > current:
      @callback
      def _on_event_start(_now):
        _LOGGER.debug(f"Event free electricity window started for account {self._account_id}")
        # Only turn on if Sunday Saver isn't already covering this (it would already be on)
        r = self._sunday_saver_result()
        if not self._evaluate_sunday_saver(r, ha_now()):
          self._state = True
          self.async_write_ha_state()
      self._cancel_event_start = async_track_point_in_time(self.hass, _on_event_start, start)
      _LOGGER.debug(f"Scheduled event free electricity start trigger at {start} for account {self._account_id}")

    if end > current:
      @callback
      def _on_event_end(_now):
        _LOGGER.debug(f"Event free electricity window ended for account {self._account_id}")
        # Event just ended — check whether Sunday Saver is still active
        r = self._sunday_saver_result()
        self._state = self._evaluate_sunday_saver(r, ha_now())
        self.async_write_ha_state()
      self._cancel_event_end = async_track_point_in_time(self.hass, _on_event_end, end)
      _LOGGER.debug(f"Scheduled event free electricity end trigger at {end} for account {self._account_id}")

  def _cancel_all_triggers(self):
    for attr in ('_cancel_start', '_cancel_end', '_cancel_event_start', '_cancel_event_end'):
      cancel = getattr(self, attr)
      if cancel:
        cancel()
        setattr(self, attr, None)

  # ── Coordinator update ─────────────────────────────────────────────────────

  @callback
  def _handle_coordinator_update(self) -> None:
    """Re-evaluate state and reschedule triggers whenever Sunday Saver coordinator refreshes."""
    result = self._sunday_saver_result()
    current = ha_now()
    self._state = self._evaluate(result, current)
    self._schedule_sunday_saver_triggers(result)
    super()._handle_coordinator_update()

  # ── Lifecycle ──────────────────────────────────────────────────────────────

  async def async_added_to_hass(self):
    """Evaluate state immediately on startup and register all triggers."""
    await super().async_added_to_hass()

    result = self.coordinator.data if self.coordinator is not None else None
    current = ha_now()
    self._state = self._evaluate(result, current)
    self._schedule_sunday_saver_triggers(result)
    self._schedule_event_triggers()
    self.async_write_ha_state()
    _LOGGER.debug(
      f"EDFEnergySundaySaverFreeElectricity initialised for account {self._account_id}: "
      f"state={self._state}"
    )

    # Safeguard: re-evaluates at :01 and :31 every minute to catch any missed triggers.
    # Not limited to Sundays since event windows can occur on any day.
    @callback
    def _safeguard(_now):
      r = self.coordinator.data if self.coordinator is not None else None
      new_state = self._evaluate(r, ha_now())
      if new_state != self._state:
        _LOGGER.debug(
          f"Free electricity safeguard corrected state from {self._state} to {new_state} "
          f"for account {self._account_id}"
        )
        self._state = new_state
        self.async_write_ha_state()

    self._cancel_safeguard = async_track_time_change(
      self.hass, _safeguard, minute=[1, 31], second=0
    )

    # Re-schedule event triggers whenever the event sensor values change
    start_id = f"sensor.edf_energy_{self._account_id}_event_free_start"
    end_id = f"sensor.edf_energy_{self._account_id}_event_free_end"

    @callback
    def _on_event_sensor_changed(_event):
      _LOGGER.debug(f"Event free electricity sensor updated for account {self._account_id}, rescheduling")
      self._schedule_event_triggers()
      r = self._sunday_saver_result()
      new_state = self._evaluate(r, ha_now())
      if new_state != self._state:
        self._state = new_state
        self.async_write_ha_state()

    self._cancel_event_sensor_tracking = async_track_state_change_event(
      self.hass, [start_id, end_id], _on_event_sensor_changed
    )

  async def async_will_remove_from_hass(self):
    """Cancel all registered listeners on removal."""
    self._cancel_all_triggers()
    if self._cancel_safeguard:
      self._cancel_safeguard()
      self._cancel_safeguard = None
    if self._cancel_event_sensor_tracking:
      self._cancel_event_sensor_tracking()
      self._cancel_event_sensor_tracking = None
