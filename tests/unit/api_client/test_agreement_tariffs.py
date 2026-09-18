"""Pricing a tariff from the account's agreement when EDF hide its product from the
pricing API (issue #32)."""
from datetime import datetime, timezone

from custom_components.edf_energy.api_client.agreement_tariffs import (
  agreement_rates_to_results,
  agreement_standing_charge,
  parse_agreement_tariffs,
)

PERIOD_FROM = datetime(2026, 9, 18, 0, 0, tzinfo=timezone.utc)
PERIOD_TO = datetime(2026, 9, 20, 0, 0, tzinfo=timezone.utc)

RESPONSE = {
  "data": {
    "account": {
      "electricityAgreements": [
        {
          "validFrom": "2026-09-09T23:00:00+00:00",
          "validTo": "2028-09-09T23:00:00+00:00",
          "tariff": {
            "__typename": "StandardTariff",
            "productCode": "EDF_SIMPLY_FIXED_2YR_SEP2028_V5",
            "tariffCode": "E-1R-EDF_SIMPLY_FIXED_2YR_SEP2028_V5-B",
            "standingCharge": 52.5,
            "unitRate": 24.99,
          },
        },
        {
          "validFrom": "2026-09-13T23:00:00+00:00",
          "validTo": "2028-03-14T00:00:00+00:00",
          "tariff": {
            "__typename": "HalfHourlyTariff",
            "productCode": "EDF_EV_FIX_GOELEC_18M_HH",
            "tariffCode": "E-1R-EDF_EV_FIX_GOELEC_18M_HH-K",
            "standingCharge": 57.84135,
            "unitRates": [
              {"value": 6.993, "validFrom": "2026-09-17T23:00:00+00:00", "validTo": "2026-09-18T05:00:00+00:00"},
              {"value": 31.7205, "validFrom": "2026-09-18T05:00:00+00:00", "validTo": "2026-09-18T22:00:00+00:00"},
              {"value": 6.993, "validFrom": "2026-09-18T22:00:00+00:00", "validTo": "2026-09-18T23:00:00+00:00"},
            ],
          },
        },
        {
          "validFrom": "2026-01-01T00:00:00+00:00",
          "validTo": None,
          "tariff": {
            "__typename": "DayNightTariff",
            "productCode": "EDF_E7",
            "tariffCode": "E-2R-EDF_E7-A",
            "standingCharge": 60.0,
            "dayRate": 30.0,
            "nightRate": 12.0,
          },
        },
        {
          "validFrom": "2026-01-01T00:00:00+00:00",
          "validTo": None,
          "tariff": {
            "__typename": "ThreeRateTariff",
            "productCode": "EDF_3R",
            "tariffCode": "E-3R-EDF_3R-A",
            "standingCharge": 60.0,
            "dayRate": 30.0,
            "nightRate": 12.0,
            "offPeakRate": 20.0,
          },
        },
      ],
      "gasAgreements": [
        {
          "validFrom": "2026-09-09T23:00:00+00:00",
          "validTo": "2028-09-09T23:00:00+00:00",
          "tariff": {
            "__typename": "GasTariffType",
            "productCode": "EDF_SIMPLY_FIXED_2YR_SEP2028_V5",
            "tariffCode": "G-1R-EDF_SIMPLY_FIXED_2YR_SEP2028_V5-B",
            "standingCharge": 29.0,
            "unitRate": 6.1,
          },
        }
      ],
    }
  }
}


def test_parse_indexes_every_agreement_by_tariff_code():
  tariffs = parse_agreement_tariffs(RESPONSE)

  assert set(tariffs) == {
    "E-1R-EDF_SIMPLY_FIXED_2YR_SEP2028_V5-B",
    "E-1R-EDF_EV_FIX_GOELEC_18M_HH-K",
    "E-2R-EDF_E7-A",
    "E-3R-EDF_3R-A",
    "G-1R-EDF_SIMPLY_FIXED_2YR_SEP2028_V5-B",
  }
  simply = tariffs["E-1R-EDF_SIMPLY_FIXED_2YR_SEP2028_V5-B"]
  assert simply["type"] == "StandardTariff"
  assert simply["unit_rate"] == 24.99
  assert simply["standing_charge"] == 52.5
  assert simply["valid_from"] == datetime(2026, 9, 9, 23, 0, tzinfo=timezone.utc)


def test_parse_tolerates_garbage():
  assert parse_agreement_tariffs(None) == {}
  assert parse_agreement_tariffs({"data": {"account": None}}) == {}
  assert parse_agreement_tariffs({"errors": [{"message": "nope"}]}) == {}


def test_standard_tariff_expands_to_half_hours_at_the_unit_rate():
  info = parse_agreement_tariffs(RESPONSE)["E-1R-EDF_SIMPLY_FIXED_2YR_SEP2028_V5-B"]

  rates = agreement_rates_to_results(info, PERIOD_FROM, PERIOD_TO)

  assert len(rates) == 96
  assert rates[0]["start"] == PERIOD_FROM
  assert rates[-1]["end"] == PERIOD_TO
  assert {r["value_inc_vat"] for r in rates} == {24.99}
  assert all(r["tariff_code"] == "E-1R-EDF_SIMPLY_FIXED_2YR_SEP2028_V5-B" for r in rates)
  assert all(r["is_capped"] is False for r in rates)


def test_price_cap_applies():
  info = parse_agreement_tariffs(RESPONSE)["E-1R-EDF_SIMPLY_FIXED_2YR_SEP2028_V5-B"]

  rates = agreement_rates_to_results(info, PERIOD_FROM, PERIOD_TO, price_cap=20.0)

  assert {r["value_inc_vat"] for r in rates} == {20.0}
  assert all(r["is_capped"] for r in rates)


def test_half_hourly_bands_are_cut_into_slots_and_clipped_to_the_period():
  info = parse_agreement_tariffs(RESPONSE)["E-1R-EDF_EV_FIX_GOELEC_18M_HH-K"]

  rates = agreement_rates_to_results(info, PERIOD_FROM, PERIOD_TO)

  # 00:00-05:00 cheap (the band started 23:00 the day before, clipped), 05:00-22:00 peak, 22:00-23:00 cheap.
  assert rates[0]["start"] == PERIOD_FROM
  assert len(rates) == 46
  assert [r["value_inc_vat"] for r in rates[:10]] == [6.993] * 10
  assert rates[10]["start"] == datetime(2026, 9, 18, 5, 0, tzinfo=timezone.utc)
  assert rates[10]["value_inc_vat"] == 31.7205
  assert rates[-1]["end"] == datetime(2026, 9, 18, 23, 0, tzinfo=timezone.utc)
  assert rates == sorted(rates, key=lambda r: r["start"])


def test_day_night_tariff_uses_the_supplied_night_rule():
  info = parse_agreement_tariffs(RESPONSE)["E-2R-EDF_E7-A"]
  is_night = lambda rate: rate["start"].hour < 7

  rates = agreement_rates_to_results(info, PERIOD_FROM, PERIOD_TO, is_night_rate=is_night)

  assert len(rates) == 96
  assert rates == sorted(rates, key=lambda r: r["start"])
  assert all(r["value_inc_vat"] == 12.0 for r in rates if r["start"].hour < 7)
  assert all(r["value_inc_vat"] == 30.0 for r in rates if r["start"].hour >= 7)


def test_day_night_without_a_night_rule_is_not_priced():
  info = parse_agreement_tariffs(RESPONSE)["E-2R-EDF_E7-A"]

  assert agreement_rates_to_results(info, PERIOD_FROM, PERIOD_TO) is None


def test_three_rate_tariff_is_not_priced_from_agreement_data():
  info = parse_agreement_tariffs(RESPONSE)["E-3R-EDF_3R-A"]

  assert agreement_rates_to_results(info, PERIOD_FROM, PERIOD_TO) is None


def test_gas_tariff_is_priced_like_a_standard_tariff():
  info = parse_agreement_tariffs(RESPONSE)["G-1R-EDF_SIMPLY_FIXED_2YR_SEP2028_V5-B"]

  rates = agreement_rates_to_results(info, PERIOD_FROM, PERIOD_TO)

  assert len(rates) == 96
  assert {r["value_inc_vat"] for r in rates} == {6.1}


def test_standing_charge_takes_the_agreement_dates():
  info = parse_agreement_tariffs(RESPONSE)["E-1R-EDF_SIMPLY_FIXED_2YR_SEP2028_V5-B"]

  charge = agreement_standing_charge(info)

  assert charge == {
    "start": datetime(2026, 9, 9, 23, 0, tzinfo=timezone.utc),
    "end": datetime(2028, 9, 9, 23, 0, tzinfo=timezone.utc),
    "value_inc_vat": 52.5,
    "tariff_code": "E-1R-EDF_SIMPLY_FIXED_2YR_SEP2028_V5-B",
  }


def test_standing_charge_missing_is_none():
  assert agreement_standing_charge(None) is None
  assert agreement_standing_charge({"tariff_code": "x", "standing_charge": None}) is None
