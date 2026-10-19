"""Filling in the days of statistics missed while the integration wasn't running.

Raised as issue #42. The previous-consumption coordinators ask EDF for the last 52 half
hours and keep the newest whole day out of that (see get_latest_day), which is the right
thing while the integration is up: a day arrives, a day is written. It also means a day
that went by with Home Assistant off, or with the integration failed, is never asked for
again. The energy dashboard keeps that gap for good - nothing in the normal path ever
looks further back than yesterday.

EDF hold half-hourly readings for far longer than that, and the integration already knows
how to import a date range, because the refresh_previous_consumption_data service does
exactly that. So this works out how far behind a meter's statistics have fallen and hands
the existing importer the first day that is missing.

Deliberately conservative:

  * A meter with no statistics at all is left alone. That is a new install, or a meter
    whose statistics the user has purged on purpose, and silently importing a fortnight of
    history in either case would be presumptuous.
  * At most BACKFILL_MAX_DAYS are filled in one go, so a long absence doesn't turn into
    hundreds of API calls on a single startup. The next startup picks up where this left
    off, and a user who wants it all at once still has the service.
  * Yesterday is left to the normal path. EDF publish readings a day or two in arrears, so
    the most recent day is often incomplete, and importing a half day of statistics would
    leave the dashboard worse off than leaving the gap.
"""
import logging
from datetime import datetime, timedelta, timezone

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import get_last_statistics
from homeassistant.core import HomeAssistant
from homeassistant.util.dt import as_local, as_utc

from ..const import DOMAIN

_LOGGER = logging.getLogger(__name__)

# How many missing days one startup will fill in.
BACKFILL_MAX_DAYS = 14

# A gap has to be at least this many days wide before it is worth filling. One day behind
# is the normal state of affairs, not a gap: EDF's readings lag the meter.
BACKFILL_MINIMUM_GAP_DAYS = 2


async def async_get_last_statistic_start(hass: HomeAssistant, statistic_id: str) -> datetime | None:
  """When the most recent statistic we wrote for this id starts, or None if there are none."""
  full_id = statistic_id if ":" in statistic_id else f"{DOMAIN}:{statistic_id}"
  stats = await get_instance(hass).async_add_executor_job(
    get_last_statistics,
    hass,
    1,
    full_id,
    True,
    {"sum"}
  )

  rows = stats.get(full_id) or []
  if not rows:
    return None

  start = rows[0].get("start")
  if start is None:
    return None

  # The recorder hands these back as unix timestamps, not datetimes.
  if isinstance(start, (int, float)):
    return datetime.fromtimestamp(start, tz=timezone.utc)
  return as_utc(start)


async def async_get_first_missing_day(
  hass: HomeAssistant,
  statistic_id: str,
  current: datetime,
  max_days: int = BACKFILL_MAX_DAYS,
) -> str | None:
  """The first day with no statistics, as YYYY-MM-DD, or None if there is nothing to do.

  `current` is now, passed in so this can be tested without freezing the clock.
  """
  last_start = await async_get_last_statistic_start(hass, statistic_id)
  if last_start is None:
    _LOGGER.debug(f"No existing statistics for {statistic_id}, so nothing to backfill")
    return None

  # Work in local days: that is what a day of statistics means to the person reading the
  # dashboard, and it is the boundary get_latest_day uses as well.
  last_day = as_local(last_start).date()
  # Yesterday is the newest day the normal path would have written.
  newest_complete_day = (as_local(current) - timedelta(days=1)).date()

  gap = (newest_complete_day - last_day).days
  if gap < BACKFILL_MINIMUM_GAP_DAYS:
    return None

  first_missing = last_day + timedelta(days=1)
  # Only reach back as far as we are willing to fill in one go, counting from the end of
  # the gap, so that the days nearest the present are the ones that get filled first.
  earliest_allowed = newest_complete_day - timedelta(days=max_days - 1)
  if first_missing < earliest_allowed:
    _LOGGER.warning(
      f"Statistics for {statistic_id} are {gap} days behind. Filling in the most recent "
      f"{max_days} days; restart again to go further back, or call the "
      f"refresh_previous_consumption_data service with an earlier date."
    )
    first_missing = earliest_allowed

  _LOGGER.info(
    f"Statistics for {statistic_id} stop at {last_day} but EDF should have readings up to "
    f"{newest_complete_day}. Importing from {first_missing}."
  )
  return first_missing.strftime("%Y-%m-%d")
