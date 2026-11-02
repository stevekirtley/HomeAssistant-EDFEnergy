"""Estimating how much was used during a free promotion.

Power Perks and the other promotions are not a tariff. EDF bill the electricity at the
ordinary rate and credit the cost back weeks later, so nothing in the published rates or in
the cost statistics marks the hours out - the only record that a window happened at all is
the session history this integration keeps.

That makes any figure here an estimate rather than a reading. It is built by laying the
session times over the hourly consumption statistics, and an hour that a session only partly
covers is apportioned by how much of it the session took, since the statistics do not go
finer than an hour.

A scheduled free window on a tariff that publishes one - FreePhase - is a different thing
entirely and is not estimated here. Those are a real rate of zero, so they already appear in
the rate breakdown and are billed as free.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.statistics import statistics_during_period

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class FreeUsageEstimate:
  """What a set of free sessions is reckoned to have covered."""

  consumption: float
  """Estimated kWh used inside the sessions."""

  cost: float
  """What those hours were charged at, and so roughly what should come back as credit."""

  sessions: int
  """How many sessions contributed to it."""

  covered_from: datetime | None
  """The earliest session held. A window reaching back before this is short of history."""


def overlap_in_hours(start: datetime, end: datetime, other_start: datetime, other_end: datetime) -> float:
  """How much of one period falls inside another, in hours."""
  first = max(start, other_start)
  last = min(end, other_end)
  if last <= first:
    return 0.0
  return (last - first).total_seconds() / 3600


def total_covered(rows, windows, tz) -> float:
  """Total of an hourly series across a set of windows, apportioning part hours."""
  total = 0.0
  for row in rows:
    row_start = row.get("start")
    if row_start is None:
      continue
    if isinstance(row_start, (int, float)):
      row_start = datetime.fromtimestamp(row_start, tz=tz)
    row_end = row_start + timedelta(hours=1)
    change = row.get("change")
    if change is None:
      continue
    covered = 0.0
    for window_start, window_end in windows:
      covered += overlap_in_hours(row_start, row_end, window_start, window_end)
    if covered <= 0:
      continue
    # Capped because overlapping sessions would otherwise count an hour more than once.
    total += float(change) * min(covered, 1.0)
  return total


def estimate_from_rows(rows, sessions, start: datetime, end: datetime,
                       cost_rows=None) -> FreeUsageEstimate:
  """Lay the sessions over hourly consumption rows and total what they cover.

  `rows` are the recorder's own, each one an hour's `change`. An hour that a session covers
  only part of contributes that fraction of its consumption - the statistics stop at an hour,
  so there is nothing finer to apportion by.
  """
  windows = [s for s in sessions if s[0] < end and s[1] > start]
  if len(windows) == 0:
    return FreeUsageEstimate(0.0, 0.0, 0, None)

  total = total_covered(rows, windows, start.tzinfo)
  # The cost series without the standing charge: a promotion credits back what the units
  # were charged at, and the standing charge is payable whether a session ran or not.
  cost = total_covered(cost_rows or [], windows, start.tzinfo)

  return FreeUsageEstimate(round(total, 3), round(cost, 2), len(windows),
                           min(w[0] for w in windows))


async def async_estimate_free_usage(hass, statistic_id: str, sessions,
                                    start: datetime, end: datetime,
                                    cost_statistic_id: str | None = None) -> FreeUsageEstimate:
  """The estimate for one meter over one window."""
  if len(sessions) == 0:
    return FreeUsageEstimate(0.0, 0.0, 0, None)

  stats = await get_instance(hass).async_add_executor_job(
    statistics_during_period,
    hass,
    start,
    end,
    # Lowercased on the way in, the way everything else that reads these does. Meter
    # serials carry letters and the statistics are written with the id folded down, so
    # asking in the API's own casing finds nothing at all and reads as no usage.
    {statistic_id.lower()} if cost_statistic_id is None
      else {statistic_id.lower(), cost_statistic_id.lower()},
    "hour",
    None,
    {"change"},
  )

  return estimate_from_rows(
    stats.get(statistic_id.lower()) or [], sessions, start, end,
    cost_rows=(stats.get(cost_statistic_id.lower()) or []) if cost_statistic_id else [],
  )
