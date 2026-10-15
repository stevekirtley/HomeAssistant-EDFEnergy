"""EDF's REST endpoints throw the odd 500 that clears itself within the hour (issue #48).
The callers already cope, so only the first failure of each endpoint is worth a warning."""
import logging

import pytest

from custom_components.edf_energy.api_client import EDFEnergyApiClient

CONTEXT = "Flextras booked hours for A-ABC1234/4766138"
OTHER_CONTEXT = "Flextras bookable days for A-ABC1234/4766138"

def create_client():
  return EDFEnergyApiClient(api_key="test-key")

def warnings(caplog):
  return [r for r in caplog.records if r.levelno == logging.WARNING]

def debugs(caplog):
  return [r for r in caplog.records if r.levelno == logging.DEBUG]

@pytest.mark.asyncio
async def test_when_endpoint_fails_first_time_then_warned(caplog):
  # Arrange
  client = create_client()

  # Act
  with caplog.at_level(logging.DEBUG, logger="custom_components.edf_energy.api_client"):
    client._log_rest_failure(CONTEXT, "%s returned HTTP %s", CONTEXT, 500)

  # Assert
  assert len(warnings(caplog)) == 1
  assert CONTEXT in warnings(caplog)[0].getMessage()
  assert "500" in warnings(caplog)[0].getMessage()

@pytest.mark.asyncio
async def test_when_endpoint_keeps_failing_then_repeats_go_to_debug(caplog):
  # Arrange
  client = create_client()

  # Act
  with caplog.at_level(logging.DEBUG, logger="custom_components.edf_energy.api_client"):
    for _ in range(5):
      client._log_rest_failure(CONTEXT, "%s returned HTTP %s", CONTEXT, 500)

  # Assert
  assert len(warnings(caplog)) == 1
  assert len(debugs(caplog)) == 4

@pytest.mark.asyncio
async def test_when_a_different_endpoint_fails_then_warned_separately(caplog):
  """One warning per endpoint, not one per client - the two hours endpoints fail together
  and each is worth saying once."""
  # Arrange
  client = create_client()

  # Act
  with caplog.at_level(logging.DEBUG, logger="custom_components.edf_energy.api_client"):
    client._log_rest_failure(CONTEXT, "%s failed", CONTEXT)
    client._log_rest_failure(OTHER_CONTEXT, "%s failed", OTHER_CONTEXT)

  # Assert
  assert len(warnings(caplog)) == 2

@pytest.mark.asyncio
async def test_when_endpoint_recovers_then_a_later_fault_is_warned_again(caplog):
  """A latch that never clears would hide a second, unrelated outage days later."""
  # Arrange
  client = create_client()
  client._log_rest_failure(CONTEXT, "%s failed", CONTEXT)
  caplog.clear()

  # Act
  client._rest_failures_logged.discard(CONTEXT)
  with caplog.at_level(logging.DEBUG, logger="custom_components.edf_energy.api_client"):
    client._log_rest_failure(CONTEXT, "%s failed", CONTEXT)

  # Assert
  assert len(warnings(caplog)) == 1
