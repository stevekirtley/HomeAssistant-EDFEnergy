"""Coordinator for EDF's Flextras scheme.

Flextras replaced Sunday Saver in 2026. Joining is only possible in the EDF
mobile app, so this coordinator is read-only apart from claiming the joining
bonus hours (the one write endpoint we have confirmed). See _docs/flextras_api.md.
"""
import logging
from datetime import datetime, timedelta

from homeassistant.util.dt import utcnow
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from ..const import (
  COORDINATOR_REFRESH_IN_SECONDS,
  DATA_ACCOUNT,
  DATA_CLIENT,
  DATA_FLEXTRAS,
  DATA_FLEXTRAS_COORDINATOR,
  DOMAIN,
  REFRESH_RATE_IN_MINUTES_FLEXTRAS,
)
from ..api_client import EDFEnergyApiClient
from . import BaseCoordinatorResult

_LOGGER = logging.getLogger(__name__)


class FlextrasCoordinatorResult(BaseCoordinatorResult):
  """State of an account's Flextras registration and sub-schemes."""

  registered: bool | None
  registration_date: str | None
  tastecard_date: str | None
  opted_out: bool | None
  bonus_hours_awarded: float | None
  bonus_hours_claimed: bool | None
  power_perks_signup_date: str | None
  weekend_saver_can_sign_up: bool | None
  weekend_saver_blockers: list[str]
  weekend_saver_tariff_excluded: bool
  power_perks_excluded: bool
  eligibility: dict

  def __init__(
    self,
    last_evaluated: datetime,
    request_attempts: int,
    registered: bool | None = None,
    registration_date: str | None = None,
    tastecard_date: str | None = None,
    opted_out: bool | None = None,
    bonus_hours_awarded: float | None = None,
    bonus_hours_claimed: bool | None = None,
    power_perks_signup_date: str | None = None,
    weekend_saver_can_sign_up: bool | None = None,
    weekend_saver_blockers: list[str] | None = None,
    weekend_saver_tariff_excluded: bool = False,
    power_perks_excluded: bool = False,
    eligibility: dict | None = None,
    last_error=None,
  ):
    super().__init__(last_evaluated, request_attempts, REFRESH_RATE_IN_MINUTES_FLEXTRAS, None, last_error)
    self.registered = registered
    self.registration_date = registration_date
    self.tastecard_date = tastecard_date
    self.opted_out = opted_out
    self.bonus_hours_awarded = bonus_hours_awarded
    self.bonus_hours_claimed = bonus_hours_claimed
    self.power_perks_signup_date = power_perks_signup_date
    self.weekend_saver_can_sign_up = weekend_saver_can_sign_up
    self.weekend_saver_blockers = weekend_saver_blockers or []
    self.weekend_saver_tariff_excluded = weekend_saver_tariff_excluded
    self.power_perks_excluded = power_perks_excluded
    self.eligibility = eligibility or {}


# Checklist gates whose failure is structural rather than something the customer
# can act on. A three-or-more-rate tariff excludes the account from Weekend Saver
# outright, so the scheme is hidden rather than shown as permanently blocked;
# the remaining gates (mobile number, meter health, meter points) are fixable and
# worth surfacing with EDF's own wording.
_STRUCTURAL_CHECKLIST_IDS = ("TariffType",)


def _parse_challenge_blockers(challenges: dict | None) -> tuple[bool | None, list[str], bool]:
  """Pull canSignUp and the failing checklist reasons out of the challenge screen.

  The screen is server-driven UI: a SIGNUP_BANNER component carries canSignUp,
  and a CHECKLIST component lists eligibility gates. Each gate that is invalid
  carries a human-readable title explaining what the account is missing.

  Returns (can_sign_up, blocker_titles, tariff_excluded).
  """
  if not challenges:
    return None, [], False

  can_sign_up: bool | None = None
  blockers: list[str] = []
  tariff_excluded = False

  for component in challenges.get("components") or []:
    props = component.get("props") or {}
    if component.get("type") == "SIGNUP_BANNER" and "canSignUp" in props:
      can_sign_up = props.get("canSignUp")
    elif component.get("type") == "CHECKLIST":
      for item in props.get("checkList") or []:
        if item.get("valid") is False:
          title = item.get("title")
          if title:
            blockers.append(title)
          item_id = item.get("id") or ""
          if any(marker in item_id for marker in _STRUCTURAL_CHECKLIST_IDS):
            tariff_excluded = True

  return can_sign_up, blockers, tariff_excluded


async def async_refresh_flextras(
  current: datetime,
  client: EDFEnergyApiClient,
  account_id: str,
  property_id: str | None,
  existing_result: FlextrasCoordinatorResult | None,
  power_perks_excluded: bool = False,
) -> FlextrasCoordinatorResult:
  if existing_result is not None and current < existing_result.next_refresh:
    return existing_result

  try:
    status = await client.async_get_flextras_status(account_id)

    if status is None:
      # A 404 here means the account has never been registered for Flextras,
      # which is a legitimate state rather than a failure.
      return FlextrasCoordinatorResult(
        current, 1, registered=False, power_perks_excluded=power_perks_excluded
      )

    can_sign_up: bool | None = None
    blockers: list[str] = []
    tariff_excluded = False
    eligibility: dict = {}

    if property_id is not None:
      challenges = await client.async_get_weekend_saver_challenges(account_id, property_id)
      can_sign_up, blockers, tariff_excluded = _parse_challenge_blockers(challenges)

      eligibility_response = await client.async_get_weekend_saver_eligibility(account_id, property_id)
      if eligibility_response is not None:
        eligibility = eligibility_response.get("eligibility") or {}

    return FlextrasCoordinatorResult(
      current,
      1,
      registered=status.get("registrationDate") is not None,
      registration_date=status.get("registrationDate"),
      tastecard_date=status.get("tasteCardActivationDate"),
      opted_out=status.get("optedOut"),
      bonus_hours_awarded=status.get("bonusHoursAwarded"),
      bonus_hours_claimed=status.get("claimedSignUpBonusHours"),
      power_perks_signup_date=status.get("powerPerksSignUpDate"),
      weekend_saver_can_sign_up=can_sign_up,
      weekend_saver_blockers=blockers,
      weekend_saver_tariff_excluded=tariff_excluded,
      power_perks_excluded=power_perks_excluded,
      eligibility=eligibility,
    )
  except Exception as e:
    _LOGGER.warning("Failed to refresh Flextras data for %s: %s (%s)", account_id, e, type(e).__name__)
    if existing_result is not None:
      return FlextrasCoordinatorResult(
        existing_result.last_evaluated,
        existing_result.request_attempts + 1,
        registered=existing_result.registered,
        registration_date=existing_result.registration_date,
        tastecard_date=existing_result.tastecard_date,
        opted_out=existing_result.opted_out,
        bonus_hours_awarded=existing_result.bonus_hours_awarded,
        bonus_hours_claimed=existing_result.bonus_hours_claimed,
        power_perks_signup_date=existing_result.power_perks_signup_date,
        weekend_saver_can_sign_up=existing_result.weekend_saver_can_sign_up,
        weekend_saver_blockers=existing_result.weekend_saver_blockers,
        weekend_saver_tariff_excluded=existing_result.weekend_saver_tariff_excluded,
        power_perks_excluded=existing_result.power_perks_excluded,
        eligibility=existing_result.eligibility,
        last_error=e,
      )
    return FlextrasCoordinatorResult(
      current - timedelta(minutes=REFRESH_RATE_IN_MINUTES_FLEXTRAS), 2, last_error=e
    )


# FreePhase tariffs already include free electricity events, so those customers
# cannot join Power Perks. EDF expose no API flag for this, so it is detected from
# the tariff code. This is a name-based heuristic and the only signal available -
# if EDF rename the product it will silently stop matching, which fails open
# (the scheme is shown) rather than hiding it wrongly.
_POWER_PERKS_EXCLUDED_PRODUCTS = ("FREEPHASE",)


def is_power_perks_excluded(hass, account_id: str) -> bool:
  """Whether the account's tariff rules it out of Power Perks."""
  try:
    account_result = hass.data[DOMAIN][account_id].get(DATA_ACCOUNT)
    account = getattr(account_result, "account", None) if account_result is not None else None
    for meter_point in (account or {}).get("electricity_meter_points") or []:
      for agreement in meter_point.get("agreements") or []:
        code = (agreement.get("tariff_code") or "").upper()
        if any(marker in code for marker in _POWER_PERKS_EXCLUDED_PRODUCTS):
          return True
  except Exception:
    return False
  return False


def get_property_id(hass, account_id: str) -> str | None:
  """First property id for the account, used by the weekend-saver endpoints."""
  try:
    account_result = hass.data[DOMAIN][account_id].get(DATA_ACCOUNT)
    account = getattr(account_result, "account", None) if account_result is not None else None
    property_ids = (account or {}).get("property_ids") or []
    return str(property_ids[0]) if property_ids else None
  except Exception:
    return None


async def async_setup_flextras_coordinator(hass, account_id: str, entry):
  async def async_update_flextras_data():
    current = utcnow()
    client: EDFEnergyApiClient = hass.data[DOMAIN][account_id][DATA_CLIENT]
    existing = hass.data[DOMAIN][account_id].get(DATA_FLEXTRAS.format(account_id))

    result = await async_refresh_flextras(
      current,
      client,
      account_id,
      get_property_id(hass, account_id),
      existing,
      is_power_perks_excluded(hass, account_id),
    )

    hass.data[DOMAIN][account_id][DATA_FLEXTRAS.format(account_id)] = result
    return result

  hass.data[DOMAIN][account_id][DATA_FLEXTRAS_COORDINATOR.format(account_id)] = DataUpdateCoordinator(
    hass,
    _LOGGER,
    name=f"flextras_{account_id}",
    update_method=async_update_flextras_data,
    update_interval=timedelta(seconds=COORDINATOR_REFRESH_IN_SECONDS),
    always_update=True,
  )

  # Mirrors the Sunday Saver coordinator: a failure here (e.g. account not
  # registered for Flextras) must not abort the whole config entry setup.
  await hass.data[DOMAIN][account_id][DATA_FLEXTRAS_COORDINATOR.format(account_id)].async_refresh()
