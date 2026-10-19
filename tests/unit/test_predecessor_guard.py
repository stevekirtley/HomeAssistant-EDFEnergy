"""This release refuses to load while an old folder that cannot stand down is present.

HACS decides where an integration goes from the domain in its manifest, so 21.0.0 installs
into custom_components/edfenergy_uk and leaves custom_components/edf_energy exactly where it
was. From 20.1.0 the old integration refuses to load once it sees this one alongside, so the
two can share a restart and only this one runs. Anyone who skipped 20.1.0 has an old folder
with no such guard: both would load, every entity would be created twice and the second copy
would take an entity id with a "_2" suffix - the broken automations the rename exists to
avoid. So when the leftover folder is older than the release that knows to stand down, this
one stays out of the way and says what to remove.
"""
import json

import pytest

from homeassistant.exceptions import ConfigEntryError

from custom_components.edfenergy_uk import _blocking_predecessor, _predecessor_version, async_setup_entry
from custom_components.edfenergy_uk.const import (
  DOMAIN,
  PREDECESSOR_DOMAIN,
  PREDECESSOR_STANDS_DOWN_FROM,
  REPAIR_OLD_FOLDER_PRESENT,
)


class StubConfig:
  def __init__(self, config_dir):
    self.config_dir = str(config_dir)


class StubHass:
  def __init__(self, config_dir):
    self.config = StubConfig(config_dir)
    self.data = {}


def _with_old_folder(tmp_path, version):
  """Lay down an old-domain folder, optionally with a broken or absent manifest."""
  folder = tmp_path / "custom_components" / PREDECESSOR_DOMAIN
  folder.mkdir(parents=True)
  if version == "no manifest":
    pass
  elif version == "unreadable":
    (folder / "manifest.json").write_text("{not json")
  else:
    (folder / "manifest.json").write_text(json.dumps({"domain": PREDECESSOR_DOMAIN, "version": version}))
  return StubHass(tmp_path)


# ── reading the old folder's version ─────────────────────────────────────────

def test_no_old_folder_reads_as_absent(tmp_path):
  (tmp_path / "custom_components").mkdir()

  assert _predecessor_version(StubHass(tmp_path)) is None


def test_a_version_is_read_as_numbers(tmp_path):
  assert _predecessor_version(_with_old_folder(tmp_path, "20.1.0")) == (20, 1, 0)


@pytest.mark.parametrize("version", ["unreadable", "", "not-a-version"])
def test_a_version_that_cannot_be_read_counts_as_too_old(tmp_path, version):
  # An unreadable manifest is no reason to assume the thing will behave itself.
  assert _predecessor_version(_with_old_folder(tmp_path, version)) == (0,)


def test_a_folder_without_a_manifest_is_not_an_integration_at_all(tmp_path):
  # Home Assistant will not load a folder with no manifest, so it cannot create a
  # competing entity and there is nothing to stand aside for.
  hass = _with_old_folder(tmp_path, "no manifest")

  assert _predecessor_version(hass) is None
  assert _blocking_predecessor(hass) is None


# ── deciding whether to stand aside ──────────────────────────────────────────

def test_nothing_blocks_when_the_old_folder_is_gone(tmp_path):
  (tmp_path / "custom_components").mkdir()

  assert _blocking_predecessor(StubHass(tmp_path)) is None


@pytest.mark.parametrize("version", ["20.1.0", "20.1.1", "20.2.0", "21.0.0"])
def test_a_folder_that_knows_to_stand_down_does_not_block(tmp_path, version):
  assert _blocking_predecessor(_with_old_folder(tmp_path, version)) is None


@pytest.mark.parametrize("version", ["20.0.0", "19.2.6", "19.2.2", "18.9.1"])
def test_a_folder_older_than_that_blocks_and_is_named(tmp_path, version):
  assert _blocking_predecessor(_with_old_folder(tmp_path, version)) == version


def test_an_unreadable_old_folder_blocks_as_unknown(tmp_path):
  assert _blocking_predecessor(_with_old_folder(tmp_path, "unreadable")) == "unknown"


def test_the_cutoff_is_the_release_that_learned_to_stand_down():
  # Guards the constant itself: 20.1.0 is the release that stands down, so anything below
  # it has to block. Bumping this by accident would let a pre-guard folder load alongside.
  assert PREDECESSOR_STANDS_DOWN_FROM == (20, 1, 0)


# ── what setup does about it ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_setup_stands_aside_and_registers_nothing(tmp_path, monkeypatch):
  # Arrange
  hass = _with_old_folder(tmp_path, "19.2.6")
  issues = []
  monkeypatch.setattr(
    "custom_components.edfenergy_uk.ir.async_create_issue",
    lambda hass, domain, issue_id, **kwargs: issues.append((domain, issue_id, kwargs)),
  )
  monkeypatch.setattr("custom_components.edfenergy_uk.ir.async_delete_issue", lambda *a, **k: None)

  # Act
  with pytest.raises(ConfigEntryError) as caught:
    await async_setup_entry(hass, object())

  # Assert - it gave up before touching hass.data, so no websocket command, no panel and
  # above all no entity got registered while the old folder is still there.
  assert PREDECESSOR_DOMAIN in str(caught.value)
  assert "19.2.6" in str(caught.value)
  assert hass.data == {}
  assert [(d, i) for d, i, _ in issues] == [(DOMAIN, REPAIR_OLD_FOLDER_PRESENT)]
  assert issues[0][2]["translation_key"] == "old_folder_present"
  assert issues[0][2]["translation_placeholders"]["old_version"] == "19.2.6"


# ── saying so when there is nothing to set up ────────────────────────────────
# Straight after an update every entry still belongs to the old domain, so Home Assistant
# has nothing here to set up and async_setup_entry never runs. The explanation has to come
# from async_setup or it never comes at all.

class StubConfigEntries:
  def __init__(self, old_entries):
    self._old = old_entries

  def async_entries(self, domain):
    return self._old if domain == PREDECESSOR_DOMAIN else []


def _hass_with(tmp_path, version, old_entries):
  hass = _with_old_folder(tmp_path, version)
  hass.config_entries = StubConfigEntries(old_entries)
  return hass


@pytest.fixture
def captured_issues(monkeypatch):
  issues = []
  monkeypatch.setattr(
    "custom_components.edfenergy_uk.ir.async_create_issue",
    lambda hass, domain, issue_id, **kwargs: issues.append((issue_id, kwargs)),
  )
  monkeypatch.setattr("custom_components.edfenergy_uk.ir.async_delete_issue", lambda *a, **k: None)
  return issues


@pytest.mark.asyncio
async def test_setup_explains_itself_when_entries_are_waiting(tmp_path, captured_issues):
  from custom_components.edfenergy_uk import async_setup

  hass = _hass_with(tmp_path, "19.2.6", [object()])

  assert await async_setup(hass, {}) is True
  assert [i for i, _ in captured_issues] == [REPAIR_OLD_FOLDER_PRESENT]
  assert captured_issues[0][1]["translation_placeholders"]["old_version"] == "19.2.6"


@pytest.mark.asyncio
async def test_setup_says_nothing_when_there_is_nothing_to_take_over(tmp_path, captured_issues):
  # An old folder lying about on a fresh install is not worth complaining about.
  from custom_components.edfenergy_uk import async_setup

  hass = _hass_with(tmp_path, "19.2.6", [])

  assert await async_setup(hass, {}) is True
  assert captured_issues == []


@pytest.mark.asyncio
async def test_setup_does_not_hand_over_while_the_old_folder_could_still_run(tmp_path, captured_issues, monkeypatch):
  # The hand-over removes config entries. Doing that while a pre-20.1.0 folder is still
  # loading would strand them on a domain that is about to create everything twice.
  from custom_components.edfenergy_uk import async_setup

  called = []
  async def _take_over(hass):
    called.append(True)
    return 0
  monkeypatch.setattr("custom_components.edfenergy_uk.async_take_over_old_entries", _take_over)

  await async_setup(_hass_with(tmp_path, "19.2.6", [object()]), {})

  assert called == []
