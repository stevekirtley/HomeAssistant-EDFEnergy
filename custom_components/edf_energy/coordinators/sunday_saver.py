import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from homeassistant.util.dt import (utcnow, as_utc, parse_datetime, now)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from ..const import (
  COORDINATOR_REFRESH_IN_SECONDS,
  CONFIG_MAIN_SUNDAY_SAVER_AUTO_ENROL,
  DATA_CLIENT,
  DATA_SUNDAY_SAVER,
  DATA_SUNDAY_SAVER_COORDINATOR,
  DOMAIN,
  REFRESH_RATE_IN_MINUTES_SUNDAY_SAVER,
)
from ..api_client import ApiException, EDFEnergyApiClient
from . import BaseCoordinatorResult

_LOGGER = logging.getLogger(__name__)
_UK_TZ = ZoneInfo("Europe/London")


def _parse_edf_datetime(dt_str: str) -> datetime | None:
  """Parse a Sunday Saver datetime string as UK local time.

  EDF's API returns local UK time (BST/GMT) but marks it as UTC or omits
  timezone entirely.  We strip any tz annotation and re-attach Europe/London
  before converting to UTC so that display in HA always reflects the correct
  local time.
  """
  dt = parse_datetime(dt_str)
  if dt is None:
    return None
  return as_utc(dt.replace(tzinfo=None).replace(tzinfo=_UK_TZ))


class SundaySaverCoordinatorResult(BaseCoordinatorResult):
  has_event: bool
  free_hours: float
  start: datetime | None
  end: datetime | None
  is_enrolled: bool | None

  def __init__(
    self,
    last_evaluated: datetime,
    request_attempts: int,
    has_event: bool,
    free_hours: float,
    start: datetime | None,
    end: datetime | None,
    last_error=None,
    is_enrolled: bool | None = None,
  ):
    super().__init__(last_evaluated, request_attempts, REFRESH_RATE_IN_MINUTES_SUNDAY_SAVER, None, last_error)
    self.has_event = has_event
    self.free_hours = free_hours
    self.start = start
    self.end = end
    self.is_enrolled = is_enrolled


def _get_week_start_date() -> str:
  """Return Monday of last week as YYYY-MM-DD.

  EDF's API requires this specific date anchor to return the upcoming Sunday's data.
  """
  today = now()
  days_since_monday = today.weekday()  # 0=Mon, 6=Sun
  last_monday = today - timedelta(days=days_since_monday + 7)
  return last_monday.strftime('%Y-%m-%d')


async def async_refresh_sunday_saver(
  current: datetime,
  client: EDFEnergyApiClient,
  account_id: str,
  existing_result: SundaySaverCoordinatorResult | None,
  auto_enrol: bool = False,
) -> tuple[SundaySaverCoordinatorResult, bool]:
  """Returns (result, newly_enrolled). newly_enrolled is True only on the tick
  where a fresh Sunday Saver registration was successfully POSTed."""

  if existing_result is not None and current < existing_result.next_refresh:
    return existing_result, False

  is_enrolled: bool | None = existing_result.is_enrolled if existing_result is not None else None
  newly_enrolled = False

  if auto_enrol:
    enrolled_ok, newly_enrolled = await client.async_join_sunday_saver(account_id)
    if enrolled_ok:
      is_enrolled = True
  else:
    checked = await client.async_get_sunday_saver_enrollment_status(account_id)
    if checked is not None:
      is_enrolled = checked

  week_start = _get_week_start_date()
  try:
    data = await client.async_get_sunday_saver(account_id, week_start)

    if data is None:
      _LOGGER.warning(f'Failed to retrieve Sunday Saver data for account {account_id}')
      if existing_result is not None:
        return SundaySaverCoordinatorResult(
          existing_result.last_evaluated,
          existing_result.request_attempts + 1,
          existing_result.has_event,
          existing_result.free_hours,
          existing_result.start,
          existing_result.end,
          last_error='No response received',
          is_enrolled=is_enrolled,
        ), newly_enrolled
      return SundaySaverCoordinatorResult(
        current - timedelta(minutes=REFRESH_RATE_IN_MINUTES_SUNDAY_SAVER),
        2, False, 0.0, None, None,
        last_error='No response received',
        is_enrolled=is_enrolled,
      ), newly_enrolled

    if not data:
      _LOGGER.debug(f'No Sunday Saver event this week for account {account_id}')
      return SundaySaverCoordinatorResult(current, 1, False, 0.0, None, None, is_enrolled=is_enrolled), newly_enrolled

    free_hours = float(data.get('FREE_HOURS', 0))
    if free_hours <= 0:
      _LOGGER.debug(f'Sunday Saver returned zero free hours for account {account_id}')
      return SundaySaverCoordinatorResult(current, 1, False, 0.0, None, None, is_enrolled=is_enrolled), newly_enrolled

    start_str = data.get('FREE_HOURS_START_DATETIME', '')
    end_str = data.get('FREE_HOURS_END_DATETIME', '')

    start = _parse_edf_datetime(start_str) if start_str else None
    end = (_parse_edf_datetime(end_str) + timedelta(minutes=30)) if end_str else None

    _LOGGER.debug(f'Sunday Saver event for account {account_id}: {free_hours}h starting {start}')
    return SundaySaverCoordinatorResult(current, 1, True, free_hours, start, end, is_enrolled=is_enrolled), newly_enrolled

  except Exception as e:
    if isinstance(e, ApiException) is False:
      raise

    _LOGGER.warning(f'Failed to retrieve Sunday Saver data for account {account_id}: {e}')
    if existing_result is not None:
      return SundaySaverCoordinatorResult(
        existing_result.last_evaluated,
        existing_result.request_attempts + 1,
        existing_result.has_event,
        existing_result.free_hours,
        existing_result.start,
        existing_result.end,
        last_error=e,
        is_enrolled=is_enrolled,
      ), newly_enrolled
    return SundaySaverCoordinatorResult(
      current - timedelta(minutes=REFRESH_RATE_IN_MINUTES_SUNDAY_SAVER),
      2, False, 0.0, None, None,
      last_error=e,
      is_enrolled=is_enrolled,
    ), newly_enrolled


async def async_setup_sunday_saver_coordinator(hass, account_id: str, entry):
  async def async_update_sunday_saver_data():
    current = utcnow()
    client: EDFEnergyApiClient = hass.data[DOMAIN][account_id][DATA_CLIENT]
    existing = hass.data[DOMAIN][account_id].get(DATA_SUNDAY_SAVER.format(account_id))
    # Read from entry.data first (set via Reconfigure); fall back to entry.options
    # for installs that configured this before it moved to the Reconfigure form.
    auto_enrol = entry.data.get(
      CONFIG_MAIN_SUNDAY_SAVER_AUTO_ENROL,
      entry.options.get(CONFIG_MAIN_SUNDAY_SAVER_AUTO_ENROL, True),
    )

    result, newly_enrolled = await async_refresh_sunday_saver(
      current,
      client,
      account_id,
      existing,
      auto_enrol,
    )

    if newly_enrolled:
      hass.components.persistent_notification.async_create(
        f"Your EDF Energy account ({account_id}) has been automatically enrolled in Sunday Saver. "
        "You can opt out at any time via the integration's Reconfigure menu.",
        title="Sunday Saver: Enrolled",
        notification_id=f"edf_energy_sunday_saver_enrolled_{account_id}",
      )
      _LOGGER.info("Sunday Saver: fired persistent notification for new enrolment of account %s", account_id)

    hass.data[DOMAIN][account_id][DATA_SUNDAY_SAVER.format(account_id)] = result
    return result

  hass.data[DOMAIN][account_id][DATA_SUNDAY_SAVER_COORDINATOR.format(account_id)] = DataUpdateCoordinator(
    hass,
    _LOGGER,
    name=f"sunday_saver_{account_id}",
    update_method=async_update_sunday_saver_data,
    update_interval=timedelta(seconds=COORDINATOR_REFRESH_IN_SECONDS),
    always_update=True,
  )

  # Use async_refresh rather than async_config_entry_first_refresh so that a
  # failure (e.g. account not enrolled in Sunday Saver, or non-JSON response)
  # does not raise ConfigEntryNotReady and block the whole integration from loading.
  # All three Sunday Saver entities handle None coordinator data gracefully.
  await hass.data[DOMAIN][account_id][DATA_SUNDAY_SAVER_COORDINATOR.format(account_id)].async_refresh()
