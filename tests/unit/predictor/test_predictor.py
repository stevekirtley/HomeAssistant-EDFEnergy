"""Reading the Power Perks Predictor feeds.

These come from somebody else's site, so the cases lean on what happens when the feed is
not what we expect, as much as when it is.
"""
from datetime import timedelta

import pytest
from homeassistant.util.dt import utcnow

from custom_components.edf_energy.const import DATA_PREDICTOR, DOMAIN, PREDICTOR_CACHE_MINUTES
from custom_components.edf_energy.predictor import (
  MAX_OUTLOOK_DAYS,
  MAX_TEXT,
  async_get_predictor,
  parse_factors,
  parse_outlook,
  parse_scores,
  parse_tomorrow,
)

# Shaped on the live feeds.
OUTLOOK = {
  "generated_at": "2026-10-16T07:40:03+00:00",
  "days": [{
    "date": "2026-10-17", "lead_days": 1, "level": "unlikely", "chance": 0.027,
    "min_price": 72.8,
    "summary": "Not enough surplus expected: moderate winds, around average demand.",
    "factors": {
      "wind": {"text": "Moderate winds", "avg_gw": 9.6, "trend": "down"},
      "solar": {"text": "Good sunshine", "peak_gw": 7.2, "trend": "up"},
      "demand": {"text": "Around average", "trend": "down"},
      "weather": {"text": "Sunny spells", "temp_c": 14},
    },
  }],
}

TOMORROW = {
  "date": "2026-10-17", "status": "firm", "free": False, "marginal": False,
  "windows": [], "free_hours": 0, "cheapest_hour": "12:00", "cheapest_hour_price": 123.01,
  "night_block_possible": False, "source": "N2EX day-ahead hourly auction via Nord Pool",
}

SCORES = {
  "summary": {"outlook_scored_days": 11, "outlook_correct": 11, "dayahead_rule_note": "Matched every window."},
  "days": [{"date": "2026-09-25", "dow": "Fri", "actual": "not free", "outlook": "unlikely", "result": "correct"}],
}


# ── The outlook ───────────────────────────────────────────────────────────────

def test_the_week_ahead_is_read():
  outlook = parse_outlook(OUTLOOK)

  assert len(outlook["days"]) == 1
  day = outlook["days"][0]
  assert day["date"] == "2026-10-17"
  assert day["level"] == "unlikely"
  assert day["known_level"] == True

def test_a_chance_is_turned_into_whole_percent():
  # The site stores it as a fraction; the panel shows a percentage.
  assert parse_outlook(OUTLOOK)["days"][0]["chance"] == 3

@pytest.mark.parametrize("chance,expected", [
  (0, 0), (1, 100), (0.5, 50), (0.996, 100), (1.5, 100), (-0.2, 0), ("lots", None), (None, None),
])
def test_a_chance_is_clamped_to_something_showable(chance, expected):
  data = {"days": [{"date": "2026-10-17", "chance": chance}]}

  assert parse_outlook(data)["days"][0]["chance"] == expected

def test_an_unknown_level_is_shown_but_not_styled_as_known():
  # A new level from the site must still appear rather than vanish, but it cannot be given
  # a colour we have not thought about.
  data = {"days": [{"date": "2026-10-17", "level": "nailed on"}]}
  day = parse_outlook(data)["days"][0]

  assert day["level"] == "nailed on"
  assert day["known_level"] == False

def test_a_day_without_a_date_is_dropped():
  # The date is the only thing every row needs; without it there is nothing to label it.
  data = {"days": [{"level": "likely"}, {"date": "2026-10-18", "level": "likely"}]}

  assert [d["date"] for d in parse_outlook(data)["days"]] == ["2026-10-18"]

def test_a_feed_that_grows_is_capped():
  data = {"days": [{"date": f"2026-10-{i:02d}"} for i in range(1, 29)]}

  assert len(parse_outlook(data)["days"]) == MAX_OUTLOOK_DAYS

def test_runaway_text_is_cut_short():
  data = {"days": [{"date": "2026-10-17", "summary": "x" * 5000}]}

  assert len(parse_outlook(data)["days"][0]["summary"]) == MAX_TEXT

@pytest.mark.parametrize("data", [None, {}, {"days": "soon"}, {"days": []}, "not json", 42])
def test_a_feed_that_makes_no_sense_is_nothing(data):
  assert parse_outlook(data) is None


# ── Factors ───────────────────────────────────────────────────────────────────

def test_the_factors_keep_the_site_s_order():
  # Wind first, weather last - the same order the site reads in.
  assert [f["kind"] for f in parse_factors(OUTLOOK["days"][0]["factors"])] == \
    ["wind", "solar", "demand", "weather"]

def test_a_factor_with_no_sentence_is_skipped():
  factors = parse_factors({"wind": {"avg_gw": 9.6}, "solar": {"text": "Good sunshine"}})

  assert [f["kind"] for f in factors] == ["solar"]

def test_an_unexpected_trend_is_dropped_rather_than_drawn():
  # The trend becomes an arrow, so an unknown one would render as nothing useful.
  factors = parse_factors({"wind": {"text": "Windy", "trend": "sideways"}})

  assert factors[0]["trend"] is None

@pytest.mark.parametrize("factors", [None, [], "windy", 7])
def test_factors_that_are_not_factors_are_empty(factors):
  assert parse_factors(factors) == []


# ── Tomorrow ──────────────────────────────────────────────────────────────────

def test_tomorrow_is_read():
  tomorrow = parse_tomorrow(TOMORROW)

  assert tomorrow["date"] == "2026-10-17"
  assert tomorrow["status"] == "firm"
  assert tomorrow["free"] == False
  assert tomorrow["cheapest_hour"] == "12:00"
  assert tomorrow["cheapest_hour_price"] == 123.01

def test_a_free_day_with_windows_is_read():
  data = {**TOMORROW, "free": True, "free_hours": 4,
          "windows": [{"start": "11:00", "end": "15:00"}]}
  tomorrow = parse_tomorrow(data)

  assert tomorrow["free"] == True
  assert tomorrow["windows"] == [{"start": "11:00", "end": "15:00"}]

def test_windows_given_as_plain_text_still_work():
  # Guarding the shape rather than assuming it: a string window must not become a blank row.
  tomorrow = parse_tomorrow({**TOMORROW, "windows": ["11:00-15:00"]})

  assert tomorrow["windows"] == [{"start": "11:00-15:00", "end": None}]

@pytest.mark.parametrize("value,expected", [
  (True, True),
  (1, True),       # unambiguous, and reading it as "not free" would hide a free day
  (False, False),
  ("no", False),   # a string is not an answer, and "no" is especially not a yes
  ("true", False),
  (None, False),
  (0, False),
])
def test_free_is_only_free_when_the_feed_says_so(value, expected):
  assert parse_tomorrow({**TOMORROW, "free": value})["free"] == expected

@pytest.mark.parametrize("data", [None, {}, {"status": "firm"}, "nope"])
def test_tomorrow_without_a_date_is_nothing(data):
  assert parse_tomorrow(data) is None


# ── The record ────────────────────────────────────────────────────────────────

def test_the_record_is_read():
  scores = parse_scores(SCORES)

  assert scores["correct"] == 11
  assert scores["scored_days"] == 11
  assert scores["note"] == "Matched every window."
  assert len(scores["days"]) == 1

@pytest.mark.parametrize("data", [None, {}, {"summary": "good"}, "nope"])
def test_a_record_without_a_summary_is_nothing(data):
  assert parse_scores(data) is None


# ── Caching ───────────────────────────────────────────────────────────────────

class StubHass:
  def __init__(self):
    self.data = {}

@pytest.mark.asyncio
async def test_the_site_is_asked_once_within_the_cache_window(monkeypatch):
  # Flicking between tabs must not turn into a burst of requests at somebody else's site.
  calls = []
  async def fake_fetch(hass):
    calls.append(1)
    return {"outlook": parse_outlook(OUTLOOK), "tomorrow": None, "scores": None, "site": "s"}
  monkeypatch.setattr("custom_components.edf_energy.predictor.async_fetch_predictor", fake_fetch)
  hass = StubHass()
  now = utcnow()

  first = await async_get_predictor(hass, now)
  second = await async_get_predictor(hass, now + timedelta(minutes=PREDICTOR_CACHE_MINUTES - 1))

  assert len(calls) == 1
  assert first["cached"] == False
  assert second["cached"] == True

@pytest.mark.asyncio
async def test_the_site_is_asked_again_once_the_cache_is_stale(monkeypatch):
  calls = []
  async def fake_fetch(hass):
    calls.append(1)
    return {"outlook": parse_outlook(OUTLOOK), "tomorrow": None, "scores": None, "site": "s"}
  monkeypatch.setattr("custom_components.edf_energy.predictor.async_fetch_predictor", fake_fetch)
  hass = StubHass()
  now = utcnow()

  await async_get_predictor(hass, now)
  await async_get_predictor(hass, now + timedelta(minutes=PREDICTOR_CACHE_MINUTES + 1))

  assert len(calls) == 2

@pytest.mark.asyncio
async def test_a_failed_fetch_is_not_cached(monkeypatch):
  # Otherwise one blip would have the tab insisting the site is down for a quarter of an hour.
  calls = []
  async def fake_fetch(hass):
    calls.append(1)
    return {"outlook": None, "tomorrow": None, "scores": None, "site": "s"}
  monkeypatch.setattr("custom_components.edf_energy.predictor.async_fetch_predictor", fake_fetch)
  hass = StubHass()
  now = utcnow()

  await async_get_predictor(hass, now)
  await async_get_predictor(hass, now + timedelta(seconds=1))

  assert len(calls) == 2
  assert hass.data.get(DOMAIN, {}).get(DATA_PREDICTOR) is None
