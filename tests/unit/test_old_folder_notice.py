"""Once this integration is running, the folder it replaced is only a tidy-up job.

The hand-over is driven from the config flow (see test_take_over_trigger.py). By the time
async_setup_entry runs, the entries belong to this domain and the old folder holds nothing,
so it loads nothing and breaks nothing.

An earlier design had this refuse to load while an old folder was present, to avoid racing
it for the entity ids. That was built on the assumption that this integration gets a chance
to run before the user does anything, which it does not: Home Assistant only sets a domain
up when something already refers to it. Refusing to load therefore achieved nothing except
taking the account offline.
"""
import json

import pytest

from custom_components.edfenergy_uk import _old_folder_present, async_setup_entry
from custom_components.edfenergy_uk.const import (
  DOMAIN,
  PREDECESSOR_DOMAIN,
  REPAIR_OLD_FOLDER_PRESENT,
)


class StubConfig:
  def __init__(self, config_dir):
    self.config_dir = str(config_dir)


class StubHass:
  def __init__(self, config_dir):
    self.config = StubConfig(config_dir)
    self.data = {}
    self.executor_jobs = []

  async def async_add_executor_job(self, func, *args):
    # Recorded as well as run: reading the manifest on the event loop makes Home Assistant
    # log a warning telling the user to report a bug against this integration.
    self.executor_jobs.append(func.__name__)
    return func(*args)


def _with_old_folder(tmp_path, version="20.1.1", manifest=True):
  folder = tmp_path / "custom_components" / PREDECESSOR_DOMAIN
  folder.mkdir(parents=True)
  if manifest is True:
    (folder / "manifest.json").write_text(json.dumps({"domain": PREDECESSOR_DOMAIN, "version": version}))
  elif manifest == "broken":
    (folder / "manifest.json").write_text("{not json")
  return StubHass(tmp_path)


def _capture_issues(monkeypatch):
  created, deleted = [], []
  monkeypatch.setattr(
    "custom_components.edfenergy_uk.ir.async_create_issue",
    lambda hass, domain, issue_id, **kwargs: created.append((domain, issue_id, kwargs)),
  )
  monkeypatch.setattr(
    "custom_components.edfenergy_uk.ir.async_delete_issue",
    lambda hass, domain, issue_id, **kwargs: deleted.append((domain, issue_id)),
  )
  return created, deleted


# ── spotting the folder ──────────────────────────────────────────────────────

def test_no_old_folder_reads_as_absent(tmp_path):
  (tmp_path / "custom_components").mkdir()

  assert _old_folder_present(StubHass(tmp_path)) is None


def test_a_missing_custom_components_directory_is_not_an_error(tmp_path):
  assert _old_folder_present(StubHass(tmp_path)) is None


def test_the_version_is_read_from_the_manifest(tmp_path):
  hass = _with_old_folder(tmp_path, version="19.2.6")

  assert _old_folder_present(hass) == "19.2.6"


def test_an_unreadable_manifest_still_counts_as_present(tmp_path):
  # The folder being there is the thing worth saying; the version is decoration.
  hass = _with_old_folder(tmp_path, manifest="broken")

  assert _old_folder_present(hass) == "unknown"


def test_a_folder_with_no_manifest_still_counts_as_present(tmp_path):
  hass = _with_old_folder(tmp_path, manifest=False)

  assert _old_folder_present(hass) == "unknown"


def test_a_file_of_that_name_does_not_count(tmp_path):
  (tmp_path / "custom_components").mkdir()
  (tmp_path / "custom_components" / PREDECESSOR_DOMAIN).write_text("not a package")

  assert _old_folder_present(StubHass(tmp_path)) is None


# ── what setup does about it ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_setup_is_not_stopped_by_the_old_folder(tmp_path, monkeypatch):
  """The failure the earlier design caused, pinned so it cannot come back.

  If this ever raises again, an account that has just been handed over goes straight back
  to having no entities.
  """
  hass = _with_old_folder(tmp_path, version="19.2.6")
  _capture_issues(monkeypatch)

  try:
    await async_setup_entry(hass, object())
  except Exception:
    # Setup wants a great deal more than a stub hass; only getting past the check matters.
    pass

  assert DOMAIN in hass.data, "setup gave up at the old folder check instead of carrying on"


@pytest.mark.asyncio
async def test_a_notice_says_the_old_folder_can_go(tmp_path, monkeypatch):
  hass = _with_old_folder(tmp_path, version="20.1.1")
  created, deleted = _capture_issues(monkeypatch)

  try:
    await async_setup_entry(hass, object())
  except Exception:
    pass

  assert [(d, i) for d, i, _ in created] == [(DOMAIN, REPAIR_OLD_FOLDER_PRESENT)]
  kwargs = created[0][2]
  assert kwargs["translation_key"] == "old_folder_present"
  assert kwargs["is_fixable"] is True, "the notice must carry a Delete button"
  # A warning, not an error: nothing is broken, there is just a folder doing nothing.
  assert kwargs["severity"].value == "warning"
  assert kwargs["translation_placeholders"] == {
    "old_domain": PREDECESSOR_DOMAIN,
    "new_domain": DOMAIN,
    "old_version": "20.1.1",
  }
  assert (DOMAIN, REPAIR_OLD_FOLDER_PRESENT) not in deleted


@pytest.mark.asyncio
async def test_the_notice_is_cleared_once_the_folder_is_gone(tmp_path, monkeypatch):
  hass = StubHass(tmp_path)
  created, deleted = _capture_issues(monkeypatch)

  try:
    await async_setup_entry(hass, object())
  except Exception:
    pass

  assert (DOMAIN, REPAIR_OLD_FOLDER_PRESENT) in deleted
  assert [i for _, i, _ in created if i == REPAIR_OLD_FOLDER_PRESENT] == []

@pytest.mark.asyncio
async def test_the_manifest_is_read_off_the_event_loop(tmp_path, monkeypatch):
  """Reading it on the loop makes Home Assistant tell the user to report a bug on us.

  It fires for everyone between installing this version and deleting the old folder, which
  is exactly the window this notice exists for.
  """
  # Arrange
  hass = _with_old_folder(tmp_path)
  _capture_issues(monkeypatch)

  # Act
  try:
    await async_setup_entry(hass, object())
  except Exception:
    pass

  # Assert
  assert "_old_folder_present" in hass.executor_jobs
