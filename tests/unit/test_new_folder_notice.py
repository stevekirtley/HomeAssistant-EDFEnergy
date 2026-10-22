"""The old domain keeps working when the domain it becomes is installed alongside it.

HACS decides where an integration goes from the domain in its manifest, so the 21.0.0
release installs into custom_components/edfenergy_uk and leaves custom_components/edf_energy
exactly where it was. Both then sit there until somebody deletes this one.

20.1.0 refused to set up in that state, on the assumption the new one would take the config
entries over by itself. It cannot: Home Assistant only sets a domain up when something
already refers to it, so the new one does nothing at all until the user adds it from
Settings. Refusing to run therefore took the account offline for as long as it took them to
notice. So this release does the opposite - it carries on exactly as before and raises a
notice saying there is a step left.
"""
import pytest

from custom_components.edf_energy import async_setup_entry
from custom_components.edf_energy.utils.successor import successor_installed
from custom_components.edf_energy.const import (
  DOMAIN,
  REPAIR_FINISH_THE_MOVE,
  SUCCESSOR_DOMAIN,
)


class StubConfig:
  def __init__(self, config_dir):
    self.config_dir = str(config_dir)


class StubHass:
  def __init__(self, config_dir):
    self.config = StubConfig(config_dir)
    self.data = {}


def _with_custom_components(tmp_path, *domains):
  for domain in domains:
    (tmp_path / "custom_components" / domain).mkdir(parents=True)
  return StubHass(tmp_path)


def _capture_issues(monkeypatch):
  created = []
  deleted = []
  monkeypatch.setattr(
    "custom_components.edf_energy.ir.async_create_issue",
    lambda hass, domain, issue_id, **kwargs: created.append((domain, issue_id, kwargs)),
  )
  monkeypatch.setattr(
    "custom_components.edf_energy.ir.async_delete_issue",
    lambda hass, domain, issue_id, **kwargs: deleted.append((domain, issue_id)),
  )
  return created, deleted


# ── the check itself ─────────────────────────────────────────────────────────

def test_successor_is_not_installed_when_only_this_one_is(tmp_path):
  hass = _with_custom_components(tmp_path, DOMAIN)

  assert successor_installed(hass) is False


def test_successor_is_spotted_when_both_are_installed(tmp_path):
  hass = _with_custom_components(tmp_path, DOMAIN, SUCCESSOR_DOMAIN)

  assert successor_installed(hass) is True


def test_a_missing_custom_components_directory_is_not_an_error(tmp_path):
  # A container that keeps custom components elsewhere must not crash the check.
  assert successor_installed(StubHass(tmp_path)) is False


def test_a_file_of_that_name_does_not_count(tmp_path):
  # Only a directory is an installed integration.
  (tmp_path / "custom_components").mkdir()
  (tmp_path / "custom_components" / SUCCESSOR_DOMAIN).write_text("not a package")

  assert successor_installed(StubHass(tmp_path)) is False


# ── what setup does about it ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_setup_carries_on_when_the_successor_is_installed(tmp_path, monkeypatch):
  """The whole point of this release: finding the new folder must not stop anything.

  If this ever raises again, every entity on the account goes unavailable the moment HACS
  downloads version 21 - which is the failure this release exists to remove.
  """
  # Arrange
  hass = _with_custom_components(tmp_path, DOMAIN, SUCCESSOR_DOMAIN)
  _capture_issues(monkeypatch)

  # Act - setup goes on to want a good deal more than a stub hass, so let it get as far as
  # it can and only insist that it got past the check.
  try:
    await async_setup_entry(hass, object())
  except Exception:
    pass

  # Assert
  assert DOMAIN in hass.data, "setup gave up at the successor check instead of carrying on"


@pytest.mark.asyncio
async def test_a_notice_points_at_the_step_that_is_left(tmp_path, monkeypatch):
  # Arrange
  hass = _with_custom_components(tmp_path, DOMAIN, SUCCESSOR_DOMAIN)
  created, deleted = _capture_issues(monkeypatch)

  # Act
  try:
    await async_setup_entry(hass, object())
  except Exception:
    pass

  # Assert
  assert [(d, i) for d, i, _ in created] == [(DOMAIN, REPAIR_FINISH_THE_MOVE)]
  kwargs = created[0][2]
  assert kwargs["translation_key"] == "finish_the_move"
  assert kwargs["is_fixable"] is True, "the notice must carry a Fix button"
  assert kwargs["translation_placeholders"] == {
    "old_domain": DOMAIN,
    "new_domain": SUCCESSOR_DOMAIN,
  }
  assert kwargs["learn_more_url"].endswith("/repairs/new_folder/")
  assert (DOMAIN, REPAIR_FINISH_THE_MOVE) not in deleted


@pytest.mark.asyncio
async def test_the_notice_is_cleared_once_the_old_folder_is_the_only_one(tmp_path, monkeypatch):
  # Arrange - the state after somebody deletes the new folder again, having changed
  # their mind or restored a backup.
  hass = _with_custom_components(tmp_path, DOMAIN)
  created, deleted = _capture_issues(monkeypatch)

  # Act
  try:
    await async_setup_entry(hass, object())
  except Exception:
    pass

  # Assert
  assert (DOMAIN, REPAIR_FINISH_THE_MOVE) in deleted
  assert [i for _, i, _ in created if i == REPAIR_FINISH_THE_MOVE] == []
