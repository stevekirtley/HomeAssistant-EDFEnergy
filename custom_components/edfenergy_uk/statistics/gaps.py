"""Finding and filling days missing from the imported consumption statistics.

Consumption is imported a day at a time, and a day that did not arrive whole was dropped and
never asked for again, so a hole in the statistics stayed there. The graphs are drawn from
these statistics, so a hole quietly understates everything drawn over it.

Only the headline consumption series is ever checked. The peak and off peak breakdowns beside
it are written only for days whose tariff actually had a peak split, so a flat rate day holds
no breakdown rows at all and is not missing anything - on a real export meter 131 of 149 days
look like holes if you ask the breakdown series. Filling a day rewrites the breakdowns for it
anyway, the same way the ordinary import does.

Filling one is not just a matter of writing the day back. Statistics carry a running sum, and
every row after a hole was written with a sum that never counted the missing day, so the day
has to go in *and* every later sum has to move up by the day's total. Doing one without the
other trades a hole for a step.
"""
import logging
from datetime import date, datetime, timedelta

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.models import StatisticData
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics,
    statistics_during_period,
)
from homeassistant.util.dt import (as_local, as_utc, parse_datetime, start_of_local_day,
                                   utc_from_timestamp)

from ..utils import get_expected_hours_in_day

_LOGGER = logging.getLogger(__name__)

class StatisticGap:
  """A local day the statistics do not hold in full."""
  day: date
  hours_held: int
  hours_expected: int

  def __init__(self, day: date, hours_held: int, hours_expected: int):
    self.day = day
    self.hours_held = hours_held
    self.hours_expected = hours_expected

  def __repr__(self):
    return f"<StatisticGap {self.day} {self.hours_held}/{self.hours_expected}>"

  def __eq__(self, other):
    return (isinstance(other, StatisticGap)
            and self.day == other.day
            and self.hours_held == other.hours_held
            and self.hours_expected == other.hours_expected)

def supply_window(agreements: list) -> tuple:
  """When the meter point was on supply, as (first day, last day), either end possibly None.

  There is no data to be had for a day before the account came on supply or after it left,
  and a hole there is not a hole - it is the shape of the agreement. Asking EDF for it gets
  nothing back, which would otherwise read as EDF having lost it.
  """
  if agreements is None or len(agreements) < 1:
    return (None, None)

  starts = [as_utc(parse_datetime(a["start"])) for a in agreements if a.get("start") is not None]
  if len(starts) < 1:
    return (None, None)

  ends = [a.get("end") for a in agreements]
  # One open ended agreement means the supply has no end, however many closed ones sit behind it
  latest_end = None
  if all(end is not None for end in ends):
    latest_end = max(as_utc(parse_datetime(end)) for end in ends)

  return (as_local(min(starts)).date(),
          as_local(latest_end).date() if latest_end is not None else None)

def find_gaps(rows: list, current: datetime, retention_in_days: int,
              supply_start: date | None = None, supply_end: date | None = None) -> list[StatisticGap]:
  """The days between the first and last row that are short of hours.

  The edges are left alone on purpose. The first day of history begins whenever the meter
  was read rather than at midnight, and the most recent day is still being published, so
  neither is evidence of anything having gone missing.

  `supply_start` and `supply_end` bound it to the days the meter point was actually on
  supply, so a day from before the account existed is never treated as missing data.
  """
  if rows is None or len(rows) < 1:
    return []

  hours_by_day: dict = {}
  for row in rows:
    day = as_local(utc_from_timestamp(row["start"])).date()
    hours_by_day[day] = hours_by_day.get(day, 0) + 1

  days = sorted(hours_by_day.keys())
  earliest = max(days[0] + timedelta(days=1),
                 start_of_local_day(current).date() - timedelta(days=retention_in_days))
  latest = days[-1] - timedelta(days=1)

  if supply_start is not None:
    # The first day on supply starts whenever the meter was energised, not at midnight
    earliest = max(earliest, supply_start + timedelta(days=1))
  if supply_end is not None:
    latest = min(latest, supply_end - timedelta(days=1))

  gaps = []
  day = earliest
  while day <= latest:
    expected = get_expected_hours_in_day(day)
    held = hours_by_day.get(day, 0)
    if held < expected:
      gaps.append(StatisticGap(day, held, expected))
    day += timedelta(days=1)

  return gaps

async def async_find_gaps(hass, statistic_id: str, current: datetime, retention_in_days: int,
                          supply_start: date | None = None,
                          supply_end: date | None = None) -> list[StatisticGap]:
  """The days `statistic_id` is short of, newest last."""
  start = as_utc(start_of_local_day(current)) - timedelta(days=retention_in_days)

  stats = await get_instance(hass).async_add_executor_job(
    statistics_during_period,
    hass,
    start,
    as_utc(start_of_local_day(current)) + timedelta(days=1),
    {statistic_id},
    "hour",
    None,
    {"sum"},
  )

  return find_gaps(stats.get(statistic_id) or [], current, retention_in_days,
                   supply_start, supply_end)

def shift_sums(rows: list, delta: float) -> list[StatisticData]:
  """Every row moved up by `delta`, which is what filling a hole beneath them means.

  `state` is the figure for the hour itself and is left exactly as it was - only the running
  total is wrong, and only because of what was never counted below it.
  """
  shifted = []

  for row in rows:
    if row.get("sum") is None:
      continue

    shifted.append(StatisticData(
      start=utc_from_timestamp(row["start"]),
      sum=round(row["sum"] + delta, 6),
      **({"state": row["state"]} if row.get("state") is not None else {}),
    ))

  return shifted

async def async_shift_sums_from(hass, statistic_id: str, metadata, start: datetime,
                                end: datetime, delta: float) -> int:
  """Move the running total of every row from `start` on up by `delta`. Answers how many moved."""
  if delta == 0:
    return 0

  stats = await get_instance(hass).async_add_executor_job(
    statistics_during_period,
    hass,
    start,
    end,
    {statistic_id},
    "hour",
    None,
    {"sum", "state"},
  )

  shifted = shift_sums(stats.get(statistic_id) or [], delta)
  if len(shifted) > 0:
    async_add_external_statistics(hass, metadata, shifted)

  _LOGGER.debug(f"Moved {len(shifted)} rows of '{statistic_id}' up by {delta}")
  return len(shifted)

# ── Telling our problem from EDF's ────────────────────────────────────────────

GAP_FILLABLE = "fillable"
GAP_PARTIAL_AT_SOURCE = "partial_at_source"
GAP_MISSING_AT_SOURCE = "missing_at_source"

class GapAssessment:
  """What EDF turned out to hold for a day our statistics are short of.

  A day EDF can still give us is ours to fix and nobody needs telling about it. A day EDF
  does not have is not something the integration can do anything about, so it is the user
  who needs to know, with the dates and hours in hand to take to EDF.
  """
  day: date
  status: str
  hours_missing: int
  slots_held: int
  slots_expected: int

  def __init__(self, day: date, status: str, hours_missing: int, slots_held: int, slots_expected: int):
    self.day = day
    self.status = status
    self.hours_missing = hours_missing
    self.slots_held = slots_held
    self.slots_expected = slots_expected

  def to_dict(self):
    return {
      "date": self.day.isoformat(),
      "status": self.status,
      "hours_missing": self.hours_missing,
      "slots_held": self.slots_held,
      "slots_expected": self.slots_expected,
    }

  def __eq__(self, other):
    return isinstance(other, GapAssessment) and self.to_dict() == other.to_dict()

  def __repr__(self):
    return f"<GapAssessment {self.day} {self.status} {self.hours_missing}h>"

def assess_gap(day: date, slots_expected: int, consumption: list | None) -> GapAssessment:
  """Judge one day against what EDF answered for it."""
  slots_held = len(consumption) if consumption is not None else 0

  if slots_held >= slots_expected:
    return GapAssessment(day, GAP_FILLABLE, 0, slots_held, slots_expected)

  # Half hours round up - someone chasing EDF over ninety minutes should be told two hours
  # are missing rather than one.
  hours_missing = -(-(slots_expected - slots_held) // 2)
  status = GAP_MISSING_AT_SOURCE if slots_held == 0 else GAP_PARTIAL_AT_SOURCE

  return GapAssessment(day, status, hours_missing, slots_held, slots_expected)

def is_old_enough_to_chase(day: date, current: datetime, minimum_age: timedelta) -> bool:
  """Whether a day has been missing long enough to be worth anyone's attention.

  EDF publish late often enough that a day short of a few half hours yesterday means nothing.
  Age is measured from the end of the day, not its start.
  """
  return as_utc(start_of_local_day(day + timedelta(days=1))) + minimum_age <= as_utc(current)

def days_to_report(assessments: list) -> list:
  """The ones the user can actually do something about, oldest first."""
  return sorted(
    [a for a in assessments if a.status in (GAP_MISSING_AT_SOURCE, GAP_PARTIAL_AT_SOURCE)],
    key=lambda a: a.day
  )
