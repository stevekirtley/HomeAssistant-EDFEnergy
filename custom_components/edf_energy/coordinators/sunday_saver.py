import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from homeassistant.util.dt import (utcnow, as_utc, parse_datetime, now)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from ..const import (
  COORDINATOR_REFRESH_IN_SECONDS,
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

  def __init__(
    self,
    last_evaluated: datetime,
    request_attempts: int,
    has_event: bool,
    free_hours: float,
    start: datetime | None,
    end: datetime | None,
    last_error=None,
  ):
    super().__init__(last_evaluated, request_attempts, REFRESH_RATE_IN_MINUTES_SUNDAY_SAVER, None, last_error)
    self.has_event = has_event
    self.free_hours = free_hours
    self.start = start
    self.end = end


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
) -> SundaySaverCoordinatorResult:

  if existing_result is not None and current < existing_result.next_refresh:
    return existing_result

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
        )
      return SundaySaverCoordinatorResult(
        current - timedelta(minutes=REFRESH_RATE_IN_MINUTES_SUNDAY_SAVER),
        2, False, 0.0, None, None,
        last_error='No response received',
      )

    if not data:
      _LOGGER.debug(f'No Sunday Saver event this week for account {account_id}')
      return SundaySaverCoordinatorResult(current, 1, False, 0.0, None, None)

    free_hours = float(data.get('FREE_HOURS', 0))
    if free_hours <= 0:
      _LOGGER.debug(f'Sunday Saver returned zero free hours for account {account_id}')
      return SundaySaverCoordinatorResult(current, 1, False, 0.0, None, None)

    start_str = data.get('FREE_HOURS_START_DATETIME', '')
    end_str = data.get('FREE_HOURS_END_DATETIME', '')

    start = _parse_edf_datetime(start_str) if start_str else None
    end = (_parse_edf_datetime(end_str) + timedelta(minutes=30)) if end_str else None

    _LOGGER.debug(f'Sunday Saver event for account {account_id}: {free_hours}h starting {start}')
    return SundaySaverCoordinatorResult(current, 1, True, free_hours, start, end)

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
      )
    return SundaySaverCoordinatorResult(
      current - timedelta(minutes=REFRESH_RATE_IN_MINUTES_SUNDAY_SAVER),
      2, False, 0.0, None, None,
      last_error=e,
    )


async def async_setup_sunday_saver_coordinator(hass, account_id: str):
  async def async_update_sunday_saver_data():
    current = utcnow()
    client: EDFEnergyApiClient = hass.data[DOMAIN][account_id][DATA_CLIENT]
    existing = hass.data[DOMAIN][account_id].get(DATA_SUNDAY_SAVER.format(account_id))

    hass.data[DOMAIN][account_id][DATA_SUNDAY_SAVER.format(account_id)] = await async_refresh_sunday_saver(
      current,
      client,
      account_id,
      existing,
    )
    return hass.data[DOMAIN][account_id][DATA_SUNDAY_SAVER.format(account_id)]

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
