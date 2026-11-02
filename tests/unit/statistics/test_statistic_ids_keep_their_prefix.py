"""External statistic ids keep the prefix they have always been written with.

Moving the integration to `edfenergy_uk` moved these too at first, on the assumption the
recorder could rename them. It cannot. `update_statistic_id` filters the row it updates on
`source == "recorder"`, so renaming anything with a source of its own matches no rows and
returns without complaint - the caller is told nothing went wrong, and years of Energy
dashboard cost history quietly stay behind while the integration starts writing elsewhere.

So the ids do not move. The prefix is a literal, exactly like the unique_ids it is built
from, and that is what makes the migration a no-op for statistics.
"""
import re

from custom_components.edfenergy_uk.const import DOMAIN, PREDECESSOR_DOMAIN, STATISTICS_SOURCE


def test_the_source_is_the_old_domain_not_this_one():
  assert STATISTICS_SOURCE == PREDECESSOR_DOMAIN
  assert STATISTICS_SOURCE != DOMAIN


def test_no_statistic_id_is_built_from_the_current_domain():
  """The regression itself: one `{DOMAIN}:` left anywhere splits somebody's history."""
  offenders = []
  for name in ("consumption", "cost", "backfill"):
    source = open(f"custom_components/edfenergy_uk/statistics/{name}.py").read()
    for match in re.finditer(r'f"\{DOMAIN\}:|source\s*=\s*DOMAIN\b', source):
      line = source[: match.start()].count("\n") + 1
      offenders.append(f"{name}.py:{line}")
  assert offenders == [], f"statistic ids built from the current domain: {offenders}"


def test_the_built_ids_carry_the_old_prefix():
  from custom_components.edfenergy_uk.statistics.cost import (
    get_electricity_cost_statistic_unique_id,
  )

  unique_id = get_electricity_cost_statistic_unique_id("sn", "mpan", False)
  statistic_id = f"{STATISTICS_SOURCE}:{unique_id}".lower()

  assert statistic_id.startswith("edf_energy:")
  assert unique_id in statistic_id or unique_id.lower() in statistic_id
