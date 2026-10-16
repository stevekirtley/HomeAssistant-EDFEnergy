"""The Power Perks Predictor tab.

Reads the three feeds behind powerperkspredictor.app and hands them to the panel.

Two things shape this module. First, it is fetched **only while the tab is open** - there
is no coordinator, no polling and no entity, so an install whose owner never opens the tab
never contacts the site. A short cache stops flicking between tabs turning into a burst of
requests. Second, the feeds come from somewhere else, so everything is bounded on the way
in: known shapes only, lists capped, numbers coerced, text trimmed. The panel escapes what
it renders as well - neither check is a reason to skip the other.

Nothing here is written to an entity, an attribute or the recorder. It is a view of
somebody else's forecast, not state belonging to this account.
"""

import asyncio
import logging

import aiohttp
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.util.dt import utcnow

from .api_client import user_agent_value
from .const import (
  DATA_PREDICTOR,
  DOMAIN,
  INTEGRATION_VERSION,
  POWER_PERKS_PREDICTOR_OUTLOOK_URL,
  POWER_PERKS_PREDICTOR_SCORES_URL,
  POWER_PERKS_PREDICTOR_SITE,
  POWER_PERKS_PREDICTOR_TOMORROW_URL,
  PREDICTOR_CACHE_MINUTES,
)

_LOGGER = logging.getLogger(__name__)

# The outlook runs a week ahead and the record a few weeks back; these are guards against a
# feed that grows unexpectedly, not limits anybody should ever meet.
MAX_OUTLOOK_DAYS = 14
MAX_RECORD_DAYS = 30
MAX_WINDOWS = 12
MAX_TEXT = 240

# How the site turns a probability into words. It does not show a percentage anywhere, and
# putting one here would say something the site deliberately does not - a 3% and a 19% both
# read "Unlikely" there, and the difference is noise the model cannot really support.
# Thresholds are the site's own, in percent, worst to best.
CHANCE_BANDS = (
  (20, "Unlikely", "unlikely"),
  (50, "Possible", "possible"),
  (70, "Good chance", "good"),
)
TOP_BAND = ("Looks likely", "likely")

# When there is no probability to band, the site falls back to the model's level - and
# softens it on the way out, because the level on its own reads more confidently than the
# model warrants. Same mapping here so the two never disagree.
LEVEL_WORDS = {
  "likely": ("Possible", "possible"),
  "possible": ("Outside chance", "possible"),
  "unlikely": ("Unlikely", "unlikely"),
}


def _text(value, limit: int = MAX_TEXT) -> str | None:
  if not isinstance(value, str):
    return None
  cleaned = value.strip()
  return cleaned[:limit] if cleaned else None


def _number(value) -> float | None:
  if isinstance(value, bool) or not isinstance(value, (int, float)):
    return None
  return round(float(value), 3)


def _percent(value) -> float | None:
  """A 0-1 probability as percent. The site stores chances as fractions."""
  number = _number(value)
  if number is None:
    return None
  return max(0.0, min(100.0, number * 100))


def band_for(day) -> dict:
  """The words the site would show for a day, never a number.

  Reads the same fields in the same order the site does, so a day reads the same in both
  places. Falls back to the softened level word, and finally to nothing at all rather than
  inventing a confidence for a day the feed said nothing about.
  """
  if not isinstance(day, dict):
    return {"word": None, "tone": None}

  chance = None
  for key in ("chance", "max_p_free_cal", "max_p_free"):
    chance = _percent(day.get(key))
    if chance is not None:
      break

  if chance is not None:
    for threshold, word, tone in CHANCE_BANDS:
      if chance < threshold:
        return {"word": word, "tone": tone}
    return {"word": TOP_BAND[0], "tone": TOP_BAND[1]}

  level = _text(day.get("level"), 32)
  if level is None:
    return {"word": None, "tone": None}
  word, tone = LEVEL_WORDS.get(level.lower(), (level, None))
  return {"word": word, "tone": tone}


def parse_factors(factors) -> list[dict]:
  """The wind/solar/demand/weather lines, in the order the site shows them.

  Each is reduced to the sentence and the trend; the raw gigawatt figures are left behind
  because the panel has no room for them and the sentence already says it.
  """
  if not isinstance(factors, dict):
    return []

  out = []
  for key in ("wind", "solar", "demand", "weather"):
    value = factors.get(key)
    if not isinstance(value, dict):
      continue
    text = _text(value.get("text"))
    if text is None:
      continue
    trend = value.get("trend")
    out.append({
      "kind": key,
      "text": text,
      "trend": trend if trend in ("up", "down", "flat") else None,
    })
  return out


def parse_outlook(data) -> dict | None:
  """The week ahead: one entry per day with its level, chance and reasoning."""
  if not isinstance(data, dict):
    return None
  days_in = data.get("days")
  if not isinstance(days_in, list):
    return None

  days = []
  for day in days_in[:MAX_OUTLOOK_DAYS]:
    if not isinstance(day, dict):
      continue
    date = _text(day.get("date"), 32)
    if date is None:
      continue
    band = band_for(day)
    days.append({
      "date": date,
      # Words only. The percentage is deliberately not carried through to the panel - the
      # site does not show one, and a figure here would be a second opinion on his own
      # model that nobody asked for.
      "band": band["word"],
      "tone": band["tone"],
      "summary": _text(day.get("summary")),
      "factors": parse_factors(day.get("factors")),
      "min_price": _number(day.get("min_price")),
    })

  if not days:
    return None
  return {"generated_at": _text(data.get("generated_at"), 64), "days": days}


def parse_tomorrow(data) -> dict | None:
  """Tomorrow's call, which is the firm one - it reads the published auction."""
  if not isinstance(data, dict):
    return None
  date = _text(data.get("date"), 32)
  if date is None:
    return None

  windows = []
  for window in (data.get("windows") or [])[:MAX_WINDOWS]:
    if isinstance(window, dict):
      start, end = _text(window.get("start"), 32), _text(window.get("end"), 32)
      if start or end:
        windows.append({"start": start, "end": end})
    elif isinstance(window, str):
      text = _text(window, 32)
      if text:
        windows.append({"start": text, "end": None})

  return {
    "date": date,
    "status": _text(data.get("status"), 32),
    "free": data.get("free") == True,
    "marginal": data.get("marginal") == True,
    "free_hours": _number(data.get("free_hours")),
    "windows": windows,
    "cheapest_hour": _text(data.get("cheapest_hour"), 16),
    "cheapest_hour_price": _number(data.get("cheapest_hour_price")),
    "night_block_possible": data.get("night_block_possible") == True,
    "generated_at": _text(data.get("generated_at"), 64),
    "source": _text(data.get("source")),
  }


def parse_scores(data) -> dict | None:
  """How the predictor has actually done, which is the bit that earns the rest of it."""
  if not isinstance(data, dict):
    return None
  summary = data.get("summary")
  if not isinstance(summary, dict):
    return None

  days = []
  for day in (data.get("days") or [])[:MAX_RECORD_DAYS]:
    if not isinstance(day, dict):
      continue
    date = _text(day.get("date"), 32)
    if date is None:
      continue
    days.append({
      "date": date,
      "dow": _text(day.get("dow"), 8),
      "actual": _text(day.get("actual"), 32),
      "outlook": _text(day.get("outlook"), 32),
      "result": _text(day.get("result"), 32),
    })

  scored = _number(summary.get("outlook_scored_days"))
  correct = _number(summary.get("outlook_correct"))
  return {
    "scored_days": int(scored) if scored is not None else None,
    "correct": int(correct) if correct is not None else None,
    "note": _text(summary.get("dayahead_rule_note"), 400),
    "days": days,
  }


async def _async_get_json(session, url: str):
  headers = {"User-Agent": f"{user_agent_value}/{INTEGRATION_VERSION}"}
  try:
    async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=20)) as response:
      if response.status != 200:
        _LOGGER.debug("Predictor feed %s returned HTTP %s", url, response.status)
        return None
      return await response.json(content_type=None)
  except Exception as e:
    # The tab says it could not reach the site; there is nothing here worth a warning in
    # somebody's log, because nothing depends on it.
    _LOGGER.debug("Predictor feed %s unavailable (%s)", url, e)
    return None


async def async_fetch_predictor(hass) -> dict:
  """Fetch the three feeds together and reduce them to what the tab draws."""
  session = async_get_clientsession(hass)
  outlook, tomorrow, scores = await asyncio.gather(
    _async_get_json(session, POWER_PERKS_PREDICTOR_OUTLOOK_URL),
    _async_get_json(session, POWER_PERKS_PREDICTOR_TOMORROW_URL),
    _async_get_json(session, POWER_PERKS_PREDICTOR_SCORES_URL),
  )

  return {
    "outlook": parse_outlook(outlook),
    "tomorrow": parse_tomorrow(tomorrow),
    "scores": parse_scores(scores),
    "site": POWER_PERKS_PREDICTOR_SITE,
  }


async def async_get_predictor(hass, current=None) -> dict:
  """The cached answer, refetched when it is older than the cache window.

  A cache miss is the only thing that reaches the site, so opening the tab repeatedly, or
  flicking between tabs, costs one request a quarter of an hour at most.
  """
  current = current or utcnow()
  store = hass.data.setdefault(DOMAIN, {})
  cached = store.get(DATA_PREDICTOR)

  if cached is not None:
    age = (current - cached["fetched_at"]).total_seconds()
    if age < PREDICTOR_CACHE_MINUTES * 60:
      return {**cached["data"], "cached": True}

  data = await async_fetch_predictor(hass)
  # Only a fetch that found something is cached, so a blip does not stick around for a
  # quarter of an hour pretending the site is down.
  if data.get("outlook") is not None or data.get("tomorrow") is not None:
    store[DATA_PREDICTOR] = {"fetched_at": current, "data": data}
  return {**data, "cached": False}
