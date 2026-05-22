
import logging
import re
from datetime import datetime, timedelta

from homeassistant.util.dt import (as_local, as_utc, parse_datetime)

from ..const import (
  REGEX_TARIFF_PARTS,
)
from ..utils.conversions import pence_to_pounds_pence_accurate
from .rate_information import get_current_rate_information

_LOGGER = logging.getLogger(__name__)

class TariffParts:
  energy: str
  rate: str
  product_code: str
  region: str

  def __init__(self, energy: str, rate: str, product_code: str, region: str):
    self.energy = energy
    self.rate = rate
    self.product_code = product_code
    self.region = region

def get_tariff_parts(tariff_code: str) -> TariffParts:
  matches = re.search(REGEX_TARIFF_PARTS, tariff_code)
  if matches is None:
    return None
  
  # If our energy or rate isn't extracted, then assume is electricity and "single" rate as that's 
  # where our experimental tariffs are
  energy = matches.groupdict()["energy"] or "E"
  rate = matches.groupdict()["rate"] or "1R"
  product_code =matches.groupdict()["product_code"]
  region = matches.groupdict()["region"]

  return TariffParts(energy, rate, product_code, region)

class Tariff:
  product: str
  code: str

  def __init__(self, product: str, code: str):
    self.product = product
    self.code = code

def is_day_night_tariff(tariff_code: str) -> bool:
  tariff_parts = get_tariff_parts(tariff_code)
  return tariff_parts is not None and "2" in tariff_parts.rate

def get_active_tariff(utcnow: datetime, agreements):
  latest_agreement = None
  latest_valid_from = None

  # Find our latest agreement
  for agreement in agreements:
    if agreement["tariff_code"] is None:
      continue

    valid_from = as_utc(parse_datetime(agreement["start"]))

    if utcnow >= valid_from and (latest_valid_from is None or valid_from > latest_valid_from):

      latest_valid_to = None
      if "end" in agreement and agreement["end"] is not None:
        latest_valid_to = as_utc(parse_datetime(agreement["end"]))

      if latest_valid_to is None or latest_valid_to >= utcnow:
        latest_agreement = agreement
        latest_valid_from = valid_from

  if latest_agreement is not None:
    return Tariff(latest_agreement["product_code"], latest_agreement["tariff_code"])
  
  return None

def get_off_peak_cost(current: datetime, rates: list):
  # Need to use as local to ensure we get the correct from/to periods relative to our local time
  today_start = as_utc(as_local(current).replace(hour=0, minute=0, second=0, microsecond=0))
  today_end = today_start + timedelta(days=1)
  off_peak_cost = None

  rate_charges = {}
  if rates is not None:
    for rate in rates:
      if rate["start"] >= today_start and rate["end"] <= today_end:
        value = rate["value_inc_vat"]
        rate_charges[value] = (rate_charges[value] if value in rate_charges else value)
        if off_peak_cost is None or off_peak_cost > rate["value_inc_vat"]:
          off_peak_cost = rate["value_inc_vat"]

  return off_peak_cost if len(rate_charges) == 2 or len(rate_charges) == 3 else None

def is_off_peak(current: datetime, rates):
  off_peak_value = get_off_peak_cost(current, rates)

  rate_information = get_current_rate_information(rates, current)

  return (off_peak_value is not None and 
          rate_information is not None and 
          rate_information["current_rate"]["is_intelligent_adjusted"] == False and 
          pence_to_pounds_pence_accurate(off_peak_value) == rate_information["current_rate"]["value_inc_vat"])

class OffPeakTime:
  start: datetime
  end: datetime

  def __init__(self, start, end):
    self.start = start
    self.end = end

  def to_dict(self):
    return {
      "start": self.start,
      "end": self.end
    }

def get_off_peak_times(current: datetime, rates: list, include_intelligent_adjusted = False):
  off_peak_value = get_off_peak_cost(current, rates)
  times: list[OffPeakTime] = []

  if rates is not None and off_peak_value is not None:
    start = None
    rates_length = len(rates)
    for rate_index in range(rates_length):
      rate = rates[rate_index]
      if (rate["value_inc_vat"] == off_peak_value and 
          ("is_intelligent_adjusted" not in rate or rate["is_intelligent_adjusted"] == False or include_intelligent_adjusted)):
        if start is None:
          start = rate["start"]
      elif start is not None:
        end = rates[rate_index - 1]["end"]
        if end >= current:
          times.append(OffPeakTime(start, end))
        start = None
    
    if start is not None:
      end = rates[-1]["end"]
      if end >= current:
        times.append(OffPeakTime(start, end))
  else:
    _LOGGER.debug(f"Unable to determine off-peak times for current time '{current}' as we couldn't find an off-peak value or rates were null")

  return times

def get_off_peak_windows_from_rates(rates: list) -> list:
  """Extract all off-peak windows from rates across every day present in the data.

  Unlike get_off_peak_times(), this includes windows that have already ended and
  splits contiguous off-peak runs at standard/intelligent-adjusted boundaries so
  each window can be labelled independently.

  Returns a list of dicts with keys: start, end, is_intelligent_adjusted.
  """
  if not rates:
    return []

  # Group rate slots by local date so we can determine the off-peak value per day
  daily_rates: dict = {}
  for rate in rates:
    date_key = as_local(rate["start"]).date()
    daily_rates.setdefault(date_key, []).append(rate)

  windows = []
  for date_key in sorted(daily_rates.keys()):
    day_rates = sorted(daily_rates[date_key], key=lambda r: r["start"])
    unique_values = {r["value_inc_vat"] for r in day_rates}
    if len(unique_values) < 2:
      continue  # Flat-rate day — no off-peak distinction
    off_peak_value = min(unique_values)

    w_start = None
    w_intelligent = False

    for i, rate in enumerate(day_rates):
      is_off = rate["value_inc_vat"] == off_peak_value
      is_int = rate.get("is_intelligent_adjusted", False)

      if is_off:
        if w_start is None:
          w_start = rate["start"]
          w_intelligent = is_int
        elif is_int != w_intelligent:
          # Transition between standard and intelligent-adjusted within off-peak — split here
          windows.append({"start": w_start, "end": rate["start"], "is_intelligent_adjusted": w_intelligent})
          w_start = rate["start"]
          w_intelligent = is_int
      else:
        if w_start is not None:
          windows.append({"start": w_start, "end": rate["start"], "is_intelligent_adjusted": w_intelligent})
          w_start = None

    if w_start is not None:
      windows.append({"start": w_start, "end": day_rates[-1]["end"], "is_intelligent_adjusted": w_intelligent})

  return windows

def private_rates_to_public_rates(rates: list):
  if rates is None:
    return None

  new_rates = []

  for rate in rates:
    new_rate = {
      "start": as_local(rate["start"]),
      "end": as_local(rate["end"]),
      "value_inc_vat": pence_to_pounds_pence_accurate(rate["value_inc_vat"])
    }

    if "is_capped" in rate:
      new_rate["is_capped"] = rate["is_capped"]
      
    if "is_intelligent_adjusted" in rate:
      new_rate["is_intelligent_adjusted"] = rate["is_intelligent_adjusted"]

    new_rates.append(new_rate)

  return new_rates

def private_rates_to_target_timeframe_data(rates: list):
  new_rates = []

  for rate in rates:
    metadata = {}
    if "is_capped" in rate:
      metadata["is_capped"] = rate["is_capped"]
      
    if "is_intelligent_adjusted" in rate:
      metadata["is_intelligent_adjusted"] = rate["is_intelligent_adjusted"]

    new_rate = {
      "start": as_local(rate["start"]),
      "end": as_local(rate["end"]),
      "value": rate["value_inc_vat"],
      "metadata": metadata
    }

    new_rates.append(new_rate)

  return new_rates
