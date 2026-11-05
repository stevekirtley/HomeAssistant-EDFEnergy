"""The old folder's notice deletes it for you.

By the time this notice can appear the hand-over has already happened, so the folder holds
no config entries and runs nothing. Deleting it is housekeeping - but it is still rm -rf on
a directory under the user's config, so it is confirmed first and it checks what it is
about to delete rather than trusting the path.
"""
import json
import os

import pytest

from custom_components.edfenergy_uk.const import (
  DOMAIN,
  PREDECESSOR_DOMAIN,
  REPAIR_OLD_FOLDER_PRESENT,
)
from custom_components.edfenergy_uk.repairs import (
  OldFolderRepairFlow,
  async_create_fix_flow,
)


class StubConfig:
  def __init__(self, config_dir):
    self.config_dir = str(config_dir)


class StubHass:
  def __init__(self, config_dir):
    self.config = StubConfig(config_dir)
    self.data = {}

  async def async_add_executor_job(self, func, *args):
    return func(*args)


OURS = {
  "codeowners": ["@stevekirtley"],
  "documentation": "https://github.com/stevekirtley/HomeAssistant-EDFEnergy",
}

# The other EDF integration in the HACS catalog, which installs into the same directory.
THEIRS = {
  "codeowners": ["@someone-else"],
  "documentation": "https://github.com/someone-else/ha-edf-energy",
}


def _folder(tmp_path, domain, manifest_domain="__same__", with_manifest=True, owner=OURS):
  folder = tmp_path / "custom_components" / domain
  folder.mkdir(parents=True)
  (folder / "sensor.py").write_text("# some code")
  if with_manifest:
    written = domain if manifest_domain == "__same__" else manifest_domain
    (folder / "manifest.json").write_text(json.dumps({"domain": written, "version": "20.1.1", **owner}))
  return folder


def _flow(tmp_path):
  flow = OldFolderRepairFlow()
  flow.hass = StubHass(tmp_path)
  return flow


def _capture_deletes(monkeypatch):
  deleted = []
  monkeypatch.setattr(
    "custom_components.edfenergy_uk.repairs.ir.async_delete_issue",
    lambda hass, domain, issue_id: deleted.append((domain, issue_id)),
  )
  return deleted


@pytest.mark.asyncio
async def test_the_notice_opens_the_delete_flow():
  flow = await async_create_fix_flow(None, REPAIR_OLD_FOLDER_PRESENT, None)

  assert isinstance(flow, OldFolderRepairFlow)


@pytest.mark.asyncio
async def test_it_asks_before_deleting_anything(tmp_path):
  folder = _folder(tmp_path, PREDECESSOR_DOMAIN)

  result = await _flow(tmp_path).async_step_confirm(None)

  assert result["type"] == "form"
  assert result["step_id"] == "confirm"
  assert folder.is_dir(), "it deleted the folder before asking"


@pytest.mark.asyncio
async def test_submitting_deletes_the_old_folder(tmp_path, monkeypatch):
  # Arrange
  folder = _folder(tmp_path, PREDECESSOR_DOMAIN)
  mine = _folder(tmp_path, DOMAIN)
  deleted = _capture_deletes(monkeypatch)

  # Act
  result = await _flow(tmp_path).async_step_confirm({})

  # Assert
  assert not folder.exists()
  assert mine.is_dir(), "it deleted the folder this integration is running from"
  assert result["type"] == "create_entry"
  assert (DOMAIN, REPAIR_OLD_FOLDER_PRESENT) in deleted


@pytest.mark.asyncio
async def test_a_directory_holding_something_else_is_left_alone(tmp_path, monkeypatch):
  """The check that stops this deleting somebody else's integration.

  Nothing says a directory called edf_energy must be ours - a user could have put anything
  there, and the one thing that distinguishes it is what the manifest inside claims.
  """
  # Arrange
  folder = _folder(tmp_path, PREDECESSOR_DOMAIN, manifest_domain="someone_elses_thing")
  deleted = _capture_deletes(monkeypatch)

  # Act
  result = await _flow(tmp_path).async_step_confirm({})

  # Assert
  assert folder.is_dir(), "it deleted a folder belonging to another integration"
  assert result["type"] == "abort"
  assert result["reason"] == "not_the_old_folder"
  assert deleted == []


@pytest.mark.asyncio
async def test_another_integration_on_the_same_domain_is_left_alone(tmp_path, monkeypatch):
  """The same directory, the same domain, and somebody else's integration in it."""
  # Arrange
  folder = _folder(tmp_path, PREDECESSOR_DOMAIN, owner=THEIRS)
  deleted = _capture_deletes(monkeypatch)

  # Act
  result = await _flow(tmp_path).async_step_confirm({})

  # Assert
  assert folder.is_dir(), "it deleted the other EDF integration"
  assert result["reason"] == "not_the_old_folder"
  assert deleted == []


@pytest.mark.asyncio
async def test_a_folder_with_no_manifest_is_left_alone(tmp_path, monkeypatch):
  folder = _folder(tmp_path, PREDECESSOR_DOMAIN, with_manifest=False)
  deleted = _capture_deletes(monkeypatch)

  result = await _flow(tmp_path).async_step_confirm({})

  assert folder.is_dir()
  assert result["reason"] == "not_the_old_folder"
  assert deleted == []


@pytest.mark.asyncio
async def test_a_folder_that_is_already_gone_clears_the_notice(tmp_path, monkeypatch):
  # Deleted by hand while the dialog sat open.
  deleted = _capture_deletes(monkeypatch)

  result = await _flow(tmp_path).async_step_confirm({})

  assert result["type"] == "abort"
  assert result["reason"] == "already_gone"
  assert (DOMAIN, REPAIR_OLD_FOLDER_PRESENT) in deleted


@pytest.mark.asyncio
async def test_a_failure_leaves_the_notice_up(tmp_path, monkeypatch):
  _folder(tmp_path, PREDECESSOR_DOMAIN)
  deleted = _capture_deletes(monkeypatch)
  monkeypatch.setattr(
    "custom_components.edfenergy_uk.repairs.shutil.rmtree",
    lambda path: (_ for _ in ()).throw(PermissionError("read only file system")),
  )

  result = await _flow(tmp_path).async_step_confirm({})

  assert result["type"] == "abort"
  assert result["reason"] == "delete_failed"
  assert deleted == [], "the notice was cleared although the folder is still there"
