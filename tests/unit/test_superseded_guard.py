"""The old domain stands aside once the domain it becomes is installed alongside it.

HACS decides where an integration goes from the domain in its manifest, so the 21.0.0
release installs into custom_components/edfenergy_uk and leaves custom_components/edf_energy
exactly where it was. For at least one restart both are on disk. If both load, every entity
is created twice and the second copy takes an entity id with a "_2" suffix - which breaks
precisely the automations the rename is supposed to carry over untouched. So the older one
refuses to set up while the newer one is present.
"""
import pytest

from homeassistant.exceptions import ConfigEntryError

from custom_components.edf_energy import _successor_installed, async_setup_entry
from custom_components.edf_energy.const import DOMAIN, REPAIR_SUPERSEDED, SUCCESSOR_DOMAIN


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


# ── the check itself ─────────────────────────────────────────────────────────

def test_successor_is_not_installed_when_only_this_one_is(tmp_path):
  hass = _with_custom_components(tmp_path, DOMAIN)

  assert _successor_installed(hass) is False


def test_successor_is_spotted_when_both_are_installed(tmp_path):
  hass = _with_custom_components(tmp_path, DOMAIN, SUCCESSOR_DOMAIN)

  assert _successor_installed(hass) is True


def test_a_missing_custom_components_directory_is_not_an_error(tmp_path):
  # A container that keeps custom components elsewhere must not crash the check.
  assert _successor_installed(StubHass(tmp_path)) is False


def test_a_file_of_that_name_does_not_count(tmp_path):
  # Only a directory is an installed integration.
  (tmp_path / "custom_components").mkdir()
  (tmp_path / "custom_components" / SUCCESSOR_DOMAIN).write_text("not a package")

  assert _successor_installed(StubHass(tmp_path)) is False


# ── what setup does about it ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_setup_stands_down_and_registers_nothing(tmp_path, monkeypatch):
  # Arrange
  hass = _with_custom_components(tmp_path, DOMAIN, SUCCESSOR_DOMAIN)
  issues = []
  monkeypatch.setattr(
    "custom_components.edf_energy.ir.async_create_issue",
    lambda hass, domain, issue_id, **kwargs: issues.append((domain, issue_id, kwargs)),
  )
  monkeypatch.setattr("custom_components.edf_energy.ir.async_delete_issue", lambda *a, **k: None)

  # Act
  with pytest.raises(ConfigEntryError) as caught:
    await async_setup_entry(hass, object())

  # Assert - it gave up before touching hass.data, so no websocket command, no panel and
  # above all no entity got registered under the old domain.
  assert SUCCESSOR_DOMAIN in str(caught.value)
  assert hass.data == {}
  assert [(d, i) for d, i, _ in issues] == [(DOMAIN, REPAIR_SUPERSEDED)]
  assert issues[0][2]["translation_key"] == "superseded"
  assert issues[0][2]["is_fixable"] is False
