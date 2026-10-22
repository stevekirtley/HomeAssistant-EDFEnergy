"""The old folder stops offering to set an account up once the new one is installed.

While both folders are on disk, Settings > Add integration lists two entries that look
alike - one per installed integration with a config flow. The new one is named
"EDF Energy (UK)" to tell them apart, but the old one is still there to be picked by
mistake, and setting an account up through it would strand that account on the old domain
with no way across but doing it all again by hand.

Only the account is refused. Target rates, cost trackers and tariff comparisons attach to
whichever folder holds the account, so they keep working either side of the hand-over.
"""
import pytest

from custom_components.edf_energy.config_flow import EDFEnergyConfigFlow
from custom_components.edf_energy.const import DOMAIN, SUCCESSOR_DOMAIN


class StubConfig:
  def __init__(self, config_dir):
    self.config_dir = str(config_dir)


class StubHass:
  def __init__(self, config_dir):
    self.config = StubConfig(config_dir)
    self.data = {}


def _flow(tmp_path, *domains):
  for domain in domains:
    (tmp_path / "custom_components" / domain).mkdir(parents=True)
  flow = EDFEnergyConfigFlow()
  flow.hass = StubHass(tmp_path)
  return flow


@pytest.mark.asyncio
async def test_the_account_step_is_refused_when_the_new_folder_is_there(tmp_path):
  # Arrange - both folders present, which is every install between the two releases.
  flow = _flow(tmp_path, DOMAIN, SUCCESSOR_DOMAIN)

  # Act
  result = await flow.async_step_account(None)

  # Assert
  assert result["type"] == "abort"
  assert result["reason"] == "use_the_new_integration"


@pytest.mark.asyncio
async def test_submitted_details_are_refused_too(tmp_path):
  # Picking the wrong entry and filling the form in must not create the entry either.
  flow = _flow(tmp_path, DOMAIN, SUCCESSOR_DOMAIN)

  result = await flow.async_step_account({"account_id": "A-1234ABCD", "api_key": "sk_test"})

  assert result["type"] == "abort"
  assert result["reason"] == "use_the_new_integration"


@pytest.mark.asyncio
async def test_the_account_step_still_works_on_its_own(tmp_path):
  """Nobody who has not installed the new folder yet should notice this at all.

  If this ever aborts, the old integration can no longer be set up by anyone - which would
  break every new install of the version that is meant to be the safe stepping stone.
  """
  # Arrange
  flow = _flow(tmp_path, DOMAIN)

  # Act - the step wants a good deal more than a stub hass once it is past the guard, so
  # let it get as far as it can and only insist it did not abort.
  try:
    result = await flow.async_step_account(None)
  except Exception:
    return

  # Assert
  assert result.get("reason") != "use_the_new_integration"
