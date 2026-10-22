"""The notice's Fix button hands the account over without leaving the Repairs page.

The new folder cannot raise a repair of its own. Home Assistant only sets a domain up when
something already refers to it, and until the hand-over happens nothing does, so the prompt
has to come from the old folder. The work does not: this presses the button on the new
folder's own migration module, which is the version that gets tested with the entries it
creates.
"""
import pytest

from custom_components.edf_energy.const import (
  DOMAIN,
  REPAIR_FINISH_THE_MOVE,
  SUCCESSOR_DOMAIN,
)
from custom_components.edf_energy.repairs import (
  FinishTheMoveRepairFlow,
  async_create_fix_flow,
)


class StubHass:
  """Enough hass for the flow, with the import step under our control."""

  def __init__(self, module=None, import_error=None):
    self._module = module
    self._import_error = import_error
    self.imported = []

  async def async_add_import_executor_job(self, func, *args):
    self.imported.append(args)
    if self._import_error is not None:
      raise self._import_error
    return self._module


class StubMigration:
  def __init__(self, taken=1, error=None):
    self._taken = taken
    self._error = error
    self.calls = 0

  async def async_take_over_old_entries(self, hass):
    self.calls += 1
    if self._error is not None:
      raise self._error
    return self._taken


def _flow(hass):
  flow = FinishTheMoveRepairFlow()
  flow.hass = hass
  return flow


def _capture_deletes(monkeypatch):
  deleted = []
  monkeypatch.setattr(
    "custom_components.edf_energy.repairs.ir.async_delete_issue",
    lambda hass, domain, issue_id: deleted.append((domain, issue_id)),
  )
  return deleted


# ── which flow the notice opens ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_the_notice_opens_the_hand_over_flow():
  flow = await async_create_fix_flow(None, REPAIR_FINISH_THE_MOVE, None)

  assert isinstance(flow, FinishTheMoveRepairFlow)


@pytest.mark.asyncio
async def test_the_other_notices_are_unaffected():
  """The dispatcher falls through to a catch-all, so a new branch can swallow everything."""
  other = await async_create_fix_flow(None, "api_key_needed_abc123", {})

  assert not isinstance(other, FinishTheMoveRepairFlow)


# ── what it does ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_it_asks_before_doing_anything():
  migration = StubMigration()
  flow = _flow(StubHass(module=migration))

  result = await flow.async_step_confirm(None)

  assert result["type"] == "form"
  assert result["step_id"] == "confirm"
  assert result["description_placeholders"] == {
    "old_domain": DOMAIN,
    "new_domain": SUCCESSOR_DOMAIN,
  }
  assert migration.calls == 0, "it moved the account before asking"


@pytest.mark.asyncio
async def test_submitting_hands_the_entries_over(monkeypatch):
  # Arrange
  migration = StubMigration(taken=2)
  hass = StubHass(module=migration)
  deleted = _capture_deletes(monkeypatch)

  # Act
  result = await _flow(hass).async_step_confirm({})

  # Assert
  assert migration.calls == 1
  assert hass.imported == [(f"custom_components.{SUCCESSOR_DOMAIN}.migration",)]
  assert result["type"] == "create_entry"
  assert (DOMAIN, REPAIR_FINISH_THE_MOVE) in deleted


@pytest.mark.asyncio
async def test_a_new_folder_that_will_not_load_is_not_fatal(monkeypatch):
  """HACS downloads the folder but it is only importable after a restart."""
  hass = StubHass(import_error=ModuleNotFoundError("no such module"))
  deleted = _capture_deletes(monkeypatch)

  result = await _flow(hass).async_step_confirm({})

  assert result["type"] == "abort"
  assert result["reason"] == "new_folder_not_ready"
  assert deleted == [], "the notice was cleared without the move being done"


@pytest.mark.asyncio
async def test_a_failed_hand_over_leaves_the_notice_up(monkeypatch):
  migration = StubMigration(error=RuntimeError("recorder is busy"))
  deleted = _capture_deletes(monkeypatch)

  result = await _flow(StubHass(module=migration)).async_step_confirm({})

  assert result["type"] == "abort"
  assert result["reason"] == "take_over_failed"
  assert deleted == [], "the notice was cleared although the move failed"


@pytest.mark.asyncio
async def test_nothing_left_to_move_clears_the_notice(monkeypatch):
  # Somebody did it from Add integration while this dialog sat open.
  migration = StubMigration(taken=0)
  deleted = _capture_deletes(monkeypatch)

  result = await _flow(StubHass(module=migration)).async_step_confirm({})

  assert result["type"] == "abort"
  assert result["reason"] == "nothing_to_take_over"
  assert (DOMAIN, REPAIR_FINISH_THE_MOVE) in deleted
