"""Coordinator for the account's billing position.

One query behind four sensors - balance, last bill, next payment and refund status - and
the header of the account tab. It is deliberately the only part of the billing surface
that is polled: statements, transactions and referrals are fetched when somebody opens the
tab that shows them, because they are lists of a hundred rows that nothing automates
against and that have no business sitting in the recorder.
"""
import logging
from datetime import datetime, timedelta

from homeassistant.util.dt import utcnow
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from ..const import (
  COORDINATOR_REFRESH_IN_SECONDS,
  DATA_BILLING,
  DATA_BILLING_COORDINATOR,
  DATA_CLIENT,
  DOMAIN,
  REFRESH_RATE_IN_MINUTES_BILLING,
)
from ..api_client import EDFEnergyApiClient
from . import BaseCoordinatorResult

_LOGGER = logging.getLogger(__name__)


class BillingCoordinatorResult(BaseCoordinatorResult):
  """The account's balance, latest statement, payment schedule and refund position."""

  summary: dict | None

  def __init__(self, last_evaluated: datetime, request_attempts: int, summary: dict | None = None, last_error=None):
    super().__init__(last_evaluated, request_attempts, REFRESH_RATE_IN_MINUTES_BILLING, None, last_error)
    self.summary = summary


async def async_refresh_billing(
  current: datetime,
  client: EDFEnergyApiClient,
  account_id: str,
  existing_result: BillingCoordinatorResult | None,
) -> BillingCoordinatorResult:
  if existing_result is not None and current < existing_result.next_refresh:
    return existing_result

  try:
    summary = await client.async_get_billing_summary(account_id)

    if summary is None:
      # Nothing came back rather than something that failed - an account with no billing
      # history at all would look like this. The last good answer is kept if there is one.
      return BillingCoordinatorResult(
        current, 1, summary=existing_result.summary if existing_result is not None else None
      )

    return BillingCoordinatorResult(current, 1, summary=summary)
  except Exception as e:
    _LOGGER.warning("Failed to refresh billing data for %s: %s (%s)", account_id, e, type(e).__name__)
    if existing_result is not None:
      # Held rather than blanked. A sensor going unavailable because EDF had a bad minute
      # is worse than one reading a balance that is two hours old.
      return BillingCoordinatorResult(
        existing_result.last_evaluated,
        existing_result.request_attempts + 1,
        summary=existing_result.summary,
        last_error=e,
      )
    return BillingCoordinatorResult(
      current - timedelta(minutes=REFRESH_RATE_IN_MINUTES_BILLING), 2, last_error=e
    )


async def async_setup_billing_coordinator(hass, account_id: str, entry):
  async def async_update_billing_data():
    current = utcnow()
    client: EDFEnergyApiClient = hass.data[DOMAIN][account_id][DATA_CLIENT]
    existing = hass.data[DOMAIN][account_id].get(DATA_BILLING.format(account_id))

    result = await async_refresh_billing(current, client, account_id, existing)

    hass.data[DOMAIN][account_id][DATA_BILLING.format(account_id)] = result
    return result

  hass.data[DOMAIN][account_id][DATA_BILLING_COORDINATOR.format(account_id)] = DataUpdateCoordinator(
    hass,
    _LOGGER,
    name=f"billing_{account_id}",
    update_method=async_update_billing_data,
    update_interval=timedelta(seconds=COORDINATOR_REFRESH_IN_SECONDS),
    always_update=True,
  )

  # As with the other optional coordinators, a failure here must not take the config entry
  # down with it.
  await hass.data[DOMAIN][account_id][DATA_BILLING_COORDINATOR.format(account_id)].async_refresh()
