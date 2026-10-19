import logging
import datetime

from homeassistant.core import HomeAssistant
from homeassistant.components.recorder.models import StatisticMetaData, StatisticMeanType
from homeassistant.components.recorder.statistics import (
    async_add_external_statistics
)

from ..const import DOMAIN
from ..utils.rate_information import get_peak_name, get_peak_type, get_unique_rates, has_peak_rates
from . import (build_cost_statistics, async_get_last_sum)

_LOGGER = logging.getLogger(__name__)

def get_electricity_cost_statistic_unique_id(serial_number: str, mpan: str, is_export: bool):
  return f"electricity_{serial_number}_{mpan}{'_export' if is_export == True else ''}_previous_accumulative_cost"

def get_electricity_cost_statistic_name(serial_number: str, mpan: str, is_export: bool):
  return f"Electricity {serial_number} {mpan}{' Export' if is_export == True else ''} Previous Accumulative Cost"

def get_gas_cost_statistic_unique_id(serial_number: str, mpan: str):
  return f"gas_{serial_number}_{mpan}_previous_accumulative_cost"

def get_gas_cost_statistic_name(serial_number: str, mpan: str):
  return f"Gas {serial_number} {mpan} Previous Accumulative Cost"

# EDF bill a daily standing charge on top of what the meter records, so the cost statistic
# above - consumption times rate, nothing more - always reads low against the bill by that
# amount. Rather than change a statistic people already have years of history in, the full
# figure is published alongside it under its own id, and the energy dashboard docs point at
# whichever one the reader wants. See issue #47.
STANDING_CHARGE_SUFFIX = "includingsc"

def get_electricity_cost_including_standing_charge_statistic_unique_id(serial_number: str, mpan: str, is_export: bool):
  return f"{get_electricity_cost_statistic_unique_id(serial_number, mpan, is_export)}_{STANDING_CHARGE_SUFFIX}"

def get_electricity_cost_including_standing_charge_statistic_name(serial_number: str, mpan: str, is_export: bool):
  return f"{get_electricity_cost_statistic_name(serial_number, mpan, is_export)} Including Standing Charge"

def get_gas_cost_including_standing_charge_statistic_unique_id(serial_number: str, mpan: str):
  return f"{get_gas_cost_statistic_unique_id(serial_number, mpan)}_{STANDING_CHARGE_SUFFIX}"

def get_gas_cost_including_standing_charge_statistic_name(serial_number: str, mpan: str):
  return f"{get_gas_cost_statistic_name(serial_number, mpan)} Including Standing Charge"

class ImportCostStatisticsResult:
  total: float
  peak_totals: "dict[str, float]"
  total_including_standing_charge: float

  def __init__(self, total: float, peak_totals: "dict[str, float]", total_including_standing_charge: float = 0):
    self.total = total
    self.peak_totals = peak_totals
    self.total_including_standing_charge = total_including_standing_charge

async def async_import_external_statistics_from_cost(
    current: datetime,
    hass: HomeAssistant,
    unique_id: str,
    name: str,
    consumptions,
    rates,
    unit_of_measurement: str,
    consumption_key: str,
    initial_statistics: ImportCostStatisticsResult = None,
    standing_charge_in_pence: float = None,
    including_standing_charge_unique_id: str = None,
    including_standing_charge_name: str = None
  ):
  if (consumptions is None or len(consumptions) < 1 or rates is None or len(rates) < 1):
    return

  statistic_id = f"{DOMAIN}:{unique_id}".lower()

  # Our sum needs to be based from the last total, so we need to grab the last record from the previous day
  latest_total_sum = initial_statistics.total if initial_statistics is not None else await async_get_last_sum(hass, consumptions[0]["start"], statistic_id)

  unique_rates = get_unique_rates(current, rates)
  total_unique_rates = len(unique_rates)
  
  _LOGGER.debug(f"statistic_id: {statistic_id}; latest_total_sum: {latest_total_sum}; total_unique_rates: {total_unique_rates};")

  statistics = build_cost_statistics(current, consumptions, rates, consumption_key, latest_total_sum)

  async_add_external_statistics(
    hass,
    StatisticMetaData(
      has_mean=False,
      has_sum=True,
      name=name,
      source=DOMAIN,
      statistic_id=statistic_id,
      unit_of_measurement=unit_of_measurement,
      mean_type=StatisticMeanType.NONE,
      unit_class=None,
    ),
    statistics
  )

  peak_totals = {}
  if has_peak_rates(total_unique_rates):
    for index in range(0, total_unique_rates):
      peak_type = get_peak_type(total_unique_rates, index)

      _LOGGER.debug(f"Importing cost statistics for '{peak_type}'...")

      target_rate = unique_rates[index]
      peak_statistic_id = f'{statistic_id}_{peak_type}'
      latest_peak_sum = initial_statistics.peak_totals[peak_type] if initial_statistics is not None and peak_type in initial_statistics.peak_totals else await async_get_last_sum(hass, consumptions[0]["start"], peak_statistic_id)

      peak_statistics = build_cost_statistics(current, consumptions, rates, consumption_key, latest_peak_sum, target_rate)
      
      async_add_external_statistics(
        hass,
        StatisticMetaData(
          has_mean=False,
          has_sum=True,
          name=f'{name} {get_peak_name(peak_type)}',
          source=DOMAIN,
          statistic_id=peak_statistic_id,
          unit_of_measurement=unit_of_measurement,
          mean_type=StatisticMeanType.NONE,
          unit_class=None,
        ),
        peak_statistics
      )

      peak_totals[peak_type] = peak_statistics[-1]["sum"] if len(peak_statistics) > 0 and peak_statistics[-1] is not None else 0

  # The same day over again, with the standing charge folded in. Published as its own
  # statistic so the energy dashboard can show what EDF actually bill without the figure
  # above - which plenty of people already use, and which other integrations compare
  # against - moving under them. Skipped entirely when the caller has no standing charge
  # to hand, so nothing half populated gets written.
  # Carried over rather than reset when there is nothing to write, so a day EDF could not
  # price the standing charge for leaves a gap instead of restarting the running total from
  # zero and taking every day after it down with it.
  total_including_standing_charge = initial_statistics.total_including_standing_charge if initial_statistics is not None else 0
  if standing_charge_in_pence is not None and including_standing_charge_unique_id is not None:
    including_statistic_id = f"{DOMAIN}:{including_standing_charge_unique_id}".lower()
    latest_including_sum = (
      initial_statistics.total_including_standing_charge
      if initial_statistics is not None
      else await async_get_last_sum(hass, consumptions[0]["start"], including_statistic_id)
    )

    including_statistics = build_cost_statistics(
      current, consumptions, rates, consumption_key, latest_including_sum,
      standing_charge_in_pence=standing_charge_in_pence
    )

    async_add_external_statistics(
      hass,
      StatisticMetaData(
        has_mean=False,
        has_sum=True,
        name=including_standing_charge_name,
        source=DOMAIN,
        statistic_id=including_statistic_id,
        unit_of_measurement=unit_of_measurement,
        mean_type=StatisticMeanType.NONE,
        unit_class=None,
      ),
      including_statistics
    )

    total_including_standing_charge = including_statistics[-1]["sum"] if len(including_statistics) > 0 and including_statistics[-1] is not None else 0

  return ImportCostStatisticsResult(statistics[-1]["sum"] if len(statistics) > 0 and statistics[-1] is not None else 0,
                                    peak_totals,
                                    total_including_standing_charge)
