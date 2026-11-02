"""Rates and standing charges taken from the account's agreements.

EDF withdraw a product version whenever the next one launches and set it to a restricted
status for a couple of weeks so comparison sites can complete their last sign-ups. While
restricted, the product is hidden from the public pricing API: the product, its unit rates
and its standing charge all answer 404 even though customers are still on it. EDF have
confirmed this is by design.

The account's agreement in Kraken still carries the tariff it is on and what it charges,
because that is what the EDF app prices from. These helpers turn that agreement data into
the same shapes the pricing API would have produced, so the rest of the integration cannot
tell the difference.
"""
from datetime import datetime
from typing import Callable

from homeassistant.util.dt import as_utc, parse_datetime

# Kraken tariff type names, as returned in __typename.
STANDARD = "StandardTariff"
PREPAY = "PrepayTariff"
DAY_NIGHT = "DayNightTariff"
THREE_RATE = "ThreeRateTariff"
FOUR_RATE_EV = "FourRateEvTariff"
HALF_HOURLY = "HalfHourlyTariff"
GAS = "GasTariffType"

SUPPORTED_TYPES = (STANDARD, PREPAY, DAY_NIGHT, HALF_HOURLY, GAS)

agreement_tariffs_query = '''query {{
  account(accountNumber: "{account_id}") {{
    electricityAgreements(active: true) {{
      validFrom
      validTo
      meterPoint {{
        mpan
      }}
      tariff {{
        __typename
        ... on TariffType {{
          productCode
          tariffCode
          standingCharge
          preVatStandingCharge
        }}
        ... on StandardTariff {{
          unitRate
        }}
        ... on PrepayTariff {{
          unitRate
        }}
        ... on DayNightTariff {{
          dayRate
          nightRate
        }}
        ... on ThreeRateTariff {{
          dayRate
          nightRate
          offPeakRate
        }}
        ... on HalfHourlyTariff {{
          unitRates {{
            value
            validFrom
            validTo
          }}
        }}
      }}
    }}
    gasAgreements(active: true) {{
      validFrom
      validTo
      meterPoint {{
        mprn
      }}
      tariff {{
        __typename
        productCode
        tariffCode
        standingCharge
        preVatStandingCharge
        unitRate
      }}
    }}
  }}
}}'''


# Kraken caps this at 100 records; a day is only a handful of bands, so that is ample.
applicable_rates_query = '''query($accountNumber: String!, $mpxn: String!, $startAt: DateTime!, $endAt: DateTime!) {
  applicableRates(accountNumber: $accountNumber, mpxn: $mpxn, startAt: $startAt, endAt: $endAt, first: 100) {
    edges {
      node {
        value
        validFrom
        validTo
      }
    }
  }
}'''


def parse_applicable_rates(response_body) -> list[dict]:
  """The bands from an applicableRates response, as {value, valid_from, valid_to}.

  Values are exclusive of VAT - see vat_multiplier.
  """
  data = ((response_body or {}).get("data") or {}).get("applicableRates") or {}
  bands = []
  for edge in data.get("edges") or []:
    node = (edge or {}).get("node") or {}
    value = _as_float(node.get("value"))
    valid_from = _as_datetime(node.get("validFrom"))
    if value is None or valid_from is None:
      continue
    bands.append({
      "value": value,
      "valid_from": valid_from,
      "valid_to": _as_datetime(node.get("validTo")),
    })
  bands.sort(key=lambda b: b["valid_from"])
  return bands


def parse_agreement_tariffs(response_body) -> dict[str, dict]:
  """Index the agreements in a GraphQL response by tariff code.

  Each entry is a plain dict: type, product_code, tariff_code, standing_charge, valid_from,
  valid_to, plus whichever of unit_rate, day_rate, night_rate, off_peak_rate and unit_rates
  the tariff type carries. Prices are as Kraken returns them, inclusive of VAT.
  """
  account = ((response_body or {}).get("data") or {}).get("account") or {}
  tariffs: dict[str, dict] = {}
  for agreement in (account.get("electricityAgreements") or []) + (account.get("gasAgreements") or []):
    if not isinstance(agreement, dict):
      continue
    tariff = agreement.get("tariff") or {}
    code = tariff.get("tariffCode")
    if not code:
      continue
    meter_point = agreement.get("meterPoint") or {}
    tariffs[code] = {
      "type": tariff.get("__typename"),
      "product_code": tariff.get("productCode"),
      "tariff_code": code,
      # The meter number this agreement belongs to. applicableRates is keyed on it, and the
      # rate methods only receive a tariff code, so the mapping has to come from here.
      "mpxn": meter_point.get("mpan") or meter_point.get("mprn"),
      "standing_charge": _as_float(tariff.get("standingCharge")),
      "pre_vat_standing_charge": _as_float(tariff.get("preVatStandingCharge")),
      "valid_from": _as_datetime(agreement.get("validFrom")),
      "valid_to": _as_datetime(agreement.get("validTo")),
      "unit_rate": _as_float(tariff.get("unitRate")),
      "day_rate": _as_float(tariff.get("dayRate")),
      "night_rate": _as_float(tariff.get("nightRate")),
      "off_peak_rate": _as_float(tariff.get("offPeakRate")),
      "unit_rates": [
        {
          "value": _as_float(r.get("value")),
          "valid_from": _as_datetime(r.get("validFrom")),
          "valid_to": _as_datetime(r.get("validTo")),
        }
        for r in (tariff.get("unitRates") or [])
        if isinstance(r, dict) and r.get("value") is not None
      ],
    }
  return tariffs


def agreement_rates_to_results(
  info: dict,
  period_from: datetime,
  period_to: datetime,
  price_cap: float | None = None,
  is_night_rate: Callable[[dict], bool] | None = None,
) -> list | None:
  """Half-hour rate entries for the period, in the pricing API's shape, or None if the
  tariff type cannot be priced from agreement data alone.

  Three-rate and four-rate tariffs carry their prices but not their time bands, so they
  are left to the pricing API. A day/night tariff uses the same Economy 7 band rule as the
  pricing API path, passed in as is_night_rate.
  """
  tariff_type = info.get("type")
  tariff_code = info.get("tariff_code")

  if tariff_type in (STANDARD, PREPAY, GAS):
    if info.get("unit_rate") is None:
      return None
    return _expand([(info["unit_rate"], period_from, period_to)], period_from, period_to, tariff_code, price_cap)

  if tariff_type == HALF_HOURLY:
    bands = [
      (r["value"], r["valid_from"], r["valid_to"])
      for r in info.get("unit_rates") or []
      if r["value"] is not None and r["valid_from"] is not None
    ]
    return _expand(bands, period_from, period_to, tariff_code, price_cap)

  if tariff_type == DAY_NIGHT:
    if info.get("day_rate") is None or info.get("night_rate") is None or is_night_rate is None:
      return None
    day = _expand([(info["day_rate"], period_from, period_to)], period_from, period_to, tariff_code, price_cap)
    night = _expand([(info["night_rate"], period_from, period_to)], period_from, period_to, tariff_code, price_cap)
    results = [r for r in day if not is_night_rate(r)] + [r for r in night if is_night_rate(r)]
    results.sort(key=lambda r: r["start"])
    return results

  return None


def agreement_covers_period(info: dict, period_from: datetime, period_to: datetime) -> bool:
  """Whether the agreement's own rates can price the whole of the requested period.

  A flat-rate tariff carries one price with no time bands, so it covers any period. A
  half-hourly tariff only carries the bands Kraken is currently publishing, which is about
  a day either side of now, so anything older needs applicableRates instead.
  """
  if info is None:
    return False
  if info.get("type") != HALF_HOURLY:
    return info.get("unit_rate") is not None or info.get("type") in (DAY_NIGHT,)

  bands = [r for r in info.get("unit_rates") or [] if r.get("valid_from") is not None]
  if not bands:
    return False
  earliest = min(r["valid_from"] for r in bands)
  latest = max((r["valid_to"] for r in bands if r.get("valid_to") is not None), default=None)
  return earliest <= period_from and latest is not None and latest >= period_to


def vat_multiplier(info: dict) -> float:
  """How much to scale an exc-VAT price by, derived from the account's own agreement.

  applicableRates publishes exc-VAT prices only, while everything downstream expects the
  inc-VAT basis the pricing API uses. Rather than hardcode a VAT rate - electricity is
  zero-rated between October 2026 and April 2027, gas is not - the ratio is taken from a
  pair of values on the agreement itself.

  Note this is the ratio applying *now*, so a historical period that straddles a change in
  the VAT rate is priced at today's rate. That only affects a tariff whose product is
  hidden, and only across the boundary, so it is accepted rather than guessed at.
  """
  if info is None:
    return 1.0
  for inc, exc in (("standing_charge", "pre_vat_standing_charge"),):
    a, b = info.get(inc), info.get(exc)
    if a is not None and b is not None and b > 0:
      ratio = a / b
      # Guard against nonsense: VAT only ever adds, and never more than a quarter.
      if 1.0 <= ratio <= 1.25:
        return ratio
  return 1.0


def applicable_rates_to_results(
  bands: list,
  info: dict,
  period_from: datetime,
  period_to: datetime,
  price_cap: float | None = None,
) -> list:
  """Half-hour rate entries from applicableRates bands, converted to the inc-VAT basis."""
  multiplier = vat_multiplier(info)
  expanded = [
    (b["value"] * multiplier, b["valid_from"], b["valid_to"])
    for b in bands
    if b.get("value") is not None and b.get("valid_from") is not None
  ]
  return _expand(expanded, period_from, period_to, info.get("tariff_code"), price_cap)


def agreement_standing_charge(info: dict) -> dict | None:
  """The standing charge in the pricing API's shape, or None if the agreement has none."""
  if info is None or info.get("standing_charge") is None:
    return None
  return {
    "start": info.get("valid_from"),
    "end": info.get("valid_to"),
    "value_inc_vat": info["standing_charge"],
    "tariff_code": info.get("tariff_code"),
  }


def _expand(bands, period_from: datetime, period_to: datetime, tariff_code: str, price_cap: float | None) -> list:
  """Cut (value, from, to) bands into 30 minute entries clipped to the period."""
  from datetime import timedelta

  results = []
  for value, band_from, band_to in sorted(bands, key=lambda b: b[1]):
    start = max(as_utc(band_from), period_from)
    end = min(as_utc(band_to), period_to) if band_to is not None else period_to
    is_capped = False
    if price_cap is not None and value > price_cap:
      value = price_cap
      is_capped = True
    while start < end:
      slot_end = start + timedelta(minutes=30)
      results.append({
        "value_inc_vat": value,
        "start": start,
        "end": slot_end,
        "tariff_code": tariff_code,
        "is_capped": is_capped,
      })
      start = slot_end
  return results


def _as_float(value):
  try:
    return float(value) if value is not None else None
  except (TypeError, ValueError):
    return None


def _as_datetime(value):
  if not isinstance(value, str):
    return None
  parsed = parse_datetime(value)
  return as_utc(parsed) if parsed is not None else None
