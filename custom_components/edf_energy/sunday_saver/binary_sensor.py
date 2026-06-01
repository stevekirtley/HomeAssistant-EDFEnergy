import logging
from datetime import datetime

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity import generate_entity_id
from homeassistant.util.dt import now as ha_now
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.event import (
  async_track_point_in_time,
  async_track_time_change,
)

from ..coordinators.sunday_saver import SundaySaverCoordinatorResult

_LOGGER = logging.getLogger(__name__)


class EDFEnergySundaySaverFreeElectricity(CoordinatorEntity, BinarySensorEntity, RestoreEntity):
  """Binary sensor: on while currently within a Sunday Saver free electricity window.

  State is driven by three mechanisms in order of precision:
    1. Exact point-in-time triggers scheduled at the window start and end times.
    2. A safeguard that re-evaluates at :01 and :31 every Sunday in case the
       point-in-time triggers were missed (e.g. HA was busy or restarting).
    3. An immediate evaluation on HA startup so a restart mid-window is handled.
  """

  def __init__(self, hass: HomeAssistant, coordinator, account_id: str):
    CoordinatorEntity.__init__(self, coordinator)
    self._account_id = account_id
    self._state = False
    self._cancel_start = None
    self._cancel_end = None
    self._cancel_safeguard = None
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

  # ── Helpers ────────────────────────────────────────────────────────────────

  def _evaluate(self, result: SundaySaverCoordinatorResult | None, current: datetime) -> bool:
    """Return True if current time falls within the Sunday Saver window."""
    if result is None or not result.has_event:
      return False
    if result.start is None or result.end is None:
      return False
    return result.start <= current <= result.end

  def _cancel_triggers(self):
    if self._cancel_start:
      self._cancel_start()
      self._cancel_start = None
    if self._cancel_end:
      self._cancel_end()
      self._cancel_end = None

  def _schedule_triggers(self, result: SundaySaverCoordinatorResult | None):
    """Cancel stale triggers and schedule new point-in-time callbacks for start/end."""
    self._cancel_triggers()
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
        self._state = False
        self.async_write_ha_state()

      self._cancel_end = async_track_point_in_time(self.hass, _on_end, result.end)
      _LOGGER.debug(f"Scheduled Sunday Saver end trigger at {result.end} for account {self._account_id}")

  # ── Coordinator update ─────────────────────────────────────────────────────

  @callback
  def _handle_coordinator_update(self) -> None:
    """Re-evaluate state and reschedule triggers whenever coordinator refreshes."""
    result: SundaySaverCoordinatorResult = (
      self.coordinator.data
      if self.coordinator is not None and self.coordinator.data is not None
      else None
    )
    current = ha_now()
    self._state = self._evaluate(result, current)
    self._schedule_triggers(result)
    super()._handle_coordinator_update()

  # ── Lifecycle ──────────────────────────────────────────────────────────────

  async def async_added_to_hass(self):
    """Evaluate state immediately on startup and register the safeguard."""
    await super().async_added_to_hass()

    # Evaluate right away — covers HA restart during an active window
    result = self.coordinator.data if self.coordinator is not None else None
    current = ha_now()
    self._state = self._evaluate(result, current)
    self._schedule_triggers(result)
    self.async_write_ha_state()
    _LOGGER.debug(
      f"EDFEnergySundaySaverFreeElectricity initialised for account {self._account_id}: "
      f"state={self._state}"
    )

    # Safeguard: fires at :01 and :31 every minute-of-hour, Sunday-filtered
    @callback
    def _safeguard(_now):
      if ha_now().weekday() != 6:  # 6 = Sunday
        return
      r = self.coordinator.data if self.coordinator is not None else None
      new_state = self._evaluate(r, ha_now())
      if new_state != self._state:
        _LOGGER.debug(
          f"Sunday Saver safeguard corrected state from {self._state} to {new_state} "
          f"for account {self._account_id}"
        )
        self._state = new_state
        self.async_write_ha_state()

    self._cancel_safeguard = async_track_time_change(
      self.hass, _safeguard, minute=[1, 31], second=0
    )

  async def async_will_remove_from_hass(self):
    """Cancel all registered listeners on removal."""
    self._cancel_triggers()
    if self._cancel_safeguard:
      self._cancel_safeguard()
      self._cancel_safeguard = None
