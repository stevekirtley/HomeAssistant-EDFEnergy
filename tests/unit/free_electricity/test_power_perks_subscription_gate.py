"""Power Perks sessions only belong to accounts signed up to the scheme.

The relay publishes every session nationally, because EDF announce them by text to everyone in
the scheme at once, so without a gate a Weekend Saver customer - or anyone on a FreePhase tariff,
which rules Power Perks out - was handed free windows they would never get, and their battery was
told to charge for power that was not coming.
"""
from datetime import datetime, timedelta

from custom_components.edfenergy_uk.api_client.free_electricity_sessions import FreeElectricitySession
from custom_components.edfenergy_uk.const import (
  DATA_FLEXTRAS,
  DATA_FREE_ELECTRICITY_SESSIONS_HISTORY,
  DATA_POWER_PERKS,
  DOMAIN,
)
from custom_components.edfenergy_uk.coordinators.flextras import FlextrasCoordinatorResult
from custom_components.edfenergy_uk.coordinators.power_perks import PowerPerksCoordinatorResult
from custom_components.edfenergy_uk.coordinators.free_electricity_sessions import (
  refresh_free_electricity_sessions,
)

ACCOUNT_ID = "A-XXXXXX"
NOW = datetime(2026, 10, 26, 9, 0)


class FakeHass:
  def __init__(self, account_data: dict):
    self.data = {DOMAIN: {ACCOUNT_ID: account_data}}


def session(code, start: datetime, end: datetime, source="power_perks"):
  return FreeElectricitySession(code, start, end, source)


def build_hass(*, signup_date=None, registered=True, flextras=True,
               feed_sessions=None, manual_sessions=None, history=None):
  data = {}
  if flextras:
    data[DATA_FLEXTRAS.format(ACCOUNT_ID)] = FlextrasCoordinatorResult(
      NOW, 1, registered=registered, power_perks_signup_date=signup_date
    )
  data[DATA_POWER_PERKS.format(ACCOUNT_ID)] = PowerPerksCoordinatorResult(
    NOW, 1, feed_sessions or [], manual_sessions or [], feed_available=True
  )
  if history is not None:
    data[DATA_FREE_ELECTRICITY_SESSIONS_HISTORY.format(ACCOUNT_ID)] = history
  return FakeHass(data)


def run(hass, current=NOW):
  return refresh_free_electricity_sessions(current, hass, ACCOUNT_ID, None, lambda *_: None)


def codes(result):
  return {e.code for e in result.events}


FEED = [session("pp_1", NOW + timedelta(hours=2), NOW + timedelta(hours=4))]
MANUAL = [session("pp_manual", NOW + timedelta(hours=6), NOW + timedelta(hours=7))]


def test_when_signed_up_then_relay_sessions_are_published():
  hass = build_hass(signup_date="2026-09-07", feed_sessions=FEED)

  assert codes(run(hass)) == {"pp_1"}


def test_when_not_signed_up_then_relay_sessions_are_dropped():
  # registered for Flextras, but never signed up to Power Perks - a Weekend Saver customer.
  hass = build_hass(signup_date=None, registered=True, feed_sessions=FEED)

  assert codes(run(hass)) == set()


def test_when_not_signed_up_then_hand_registered_sessions_survive():
  """Registering a session by hand is a deliberate act on this instance, not the relay's doing."""
  hass = build_hass(signup_date=None, registered=True, feed_sessions=FEED, manual_sessions=MANUAL)

  assert codes(run(hass)) == {"pp_manual"}


def test_when_flextras_has_not_answered_then_relay_sessions_are_kept():
  """No Flextras data at all: unknown, not "no". Fail open rather than stop a battery charging."""
  hass = build_hass(flextras=False, feed_sessions=FEED)

  assert codes(run(hass)) == {"pp_1"}


def test_when_flextras_failed_before_any_answer_then_relay_sessions_are_kept():
  """A first-tick failure leaves registered at None, which must not read as "not signed up"."""
  hass = build_hass(registered=None, signup_date=None, feed_sessions=FEED)

  assert codes(run(hass)) == {"pp_1"}


def test_when_not_signed_up_then_future_sessions_already_in_history_are_retracted():
  """An earlier version wrote these in. They have not started, so they must go."""
  stale = session("pp_old", NOW + timedelta(hours=3), NOW + timedelta(hours=5))
  hass = build_hass(signup_date=None, registered=True, history=[stale])

  assert codes(run(hass)) == set()


def test_when_not_signed_up_then_a_session_already_under_way_is_kept():
  """Retracting a window that has already started would re-price what was imported during it."""
  started = session("pp_running", NOW - timedelta(hours=1), NOW + timedelta(hours=1))
  hass = build_hass(signup_date=None, registered=True, history=[started])

  assert codes(run(hass)) == {"pp_running"}


def test_other_sources_are_untouched_when_not_signed_up():
  booked = session("flex_1", NOW + timedelta(hours=2), NOW + timedelta(hours=3), "flextras_hours")
  hass = build_hass(signup_date=None, registered=True, feed_sessions=FEED, history=[booked])

  assert codes(run(hass)) == {"flex_1"}
