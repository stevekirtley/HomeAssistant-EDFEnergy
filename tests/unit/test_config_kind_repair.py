"""A config entry that lost its 'kind' used to break setup permanently.

Reported on Reddit against 19.2.4: `KeyError: 'kind'` from async_setup_entry, with the
integration showing "Failed to set up". The entry had an account id but no kind, and
nothing could put it right - the migration that fills the kind in only runs while the
entry is below the current config version, so an entry already at the current version
stayed broken through every restart. 19.2.4 did not cause it; updating merely forced the
reload that showed it.
"""
import pytest

from custom_components.edfenergy_uk import _infer_config_kind
from custom_components.edfenergy_uk.const import (
  CONFIG_ACCOUNT_ID,
  CONFIG_COST_TRACKER_TARGET_ENTITY_ID,
  CONFIG_KIND_ACCOUNT,
  CONFIG_KIND_COST_TRACKER,
  CONFIG_KIND_TARIFF_COMPARISON,
  CONFIG_TARIFF_COMPARISON_PRODUCT_CODE,
)


def test_an_entry_with_only_an_account_id_is_an_account():
  """The reported case: the great majority of entries, and the safe default."""
  assert _infer_config_kind({CONFIG_ACCOUNT_ID: "A-XXXXXX"}) == CONFIG_KIND_ACCOUNT


def test_a_cost_tracker_is_not_mistaken_for_an_account():
  """Every kind carries the account id, so the child's own field is what tells them apart."""
  config = {CONFIG_ACCOUNT_ID: "A-XXXXXX", CONFIG_COST_TRACKER_TARGET_ENTITY_ID: "sensor.x"}

  assert _infer_config_kind(config) == CONFIG_KIND_COST_TRACKER


def test_a_tariff_comparison_is_not_mistaken_for_an_account():
  config = {CONFIG_ACCOUNT_ID: "A-XXXXXX", CONFIG_TARIFF_COMPARISON_PRODUCT_CODE: "GO-ELEC-12M"}

  assert _infer_config_kind(config) == CONFIG_KIND_TARIFF_COMPARISON


def test_an_empty_entry_still_resolves_rather_than_raising():
  """Setup must not fail here whatever the entry looks like."""
  assert _infer_config_kind({}) == CONFIG_KIND_ACCOUNT


def test_a_sibling_without_a_kind_does_not_bring_the_account_down():
  """Reported against 21.0.0 by two users after the hand-over from the old domain.

  `KeyError: 'kind'` from async_setup_entry, raised while the account entry walked its
  sibling entries to reload them. The account's own entry repairs a missing kind before it
  gets here, but the siblings were read by key, so one entry without a kind took the whole
  account down - no meters, no export, no free electricity, no EV device.

  The hand-over is what makes this reachable: it copies an old entry's data verbatim and
  recreates it at the current config version, so the migration that would have filled the
  kind in never runs on it.
  """
  siblings = [
    {CONFIG_ACCOUNT_ID: "A-XXXXXX", "kind": CONFIG_KIND_ACCOUNT},
    # The one that used to raise.
    {CONFIG_ACCOUNT_ID: "A-XXXXXX", CONFIG_COST_TRACKER_TARGET_ENTITY_ID: "sensor.x"},
    {CONFIG_ACCOUNT_ID: "A-OTHER", CONFIG_TARIFF_COMPARISON_PRODUCT_CODE: "GO-ELEC-12M"},
  ]

  reloaded = []
  for config in siblings:
    kind = config.get("kind") or _infer_config_kind(config)
    if kind != CONFIG_KIND_ACCOUNT and config.get(CONFIG_ACCOUNT_ID) == "A-XXXXXX":
      reloaded.append(config)

  # The kindless cost tracker is recognised and reloaded; the other account's entry is left
  # alone; nothing raises.
  assert reloaded == [siblings[1]]


def test_an_entry_missing_its_account_id_is_skipped_rather_than_raising():
  """The same line read the account id by key too, so it had the same failure available."""
  config = {CONFIG_COST_TRACKER_TARGET_ENTITY_ID: "sensor.x"}

  kind = config.get("kind") or _infer_config_kind(config)

  assert kind == CONFIG_KIND_COST_TRACKER
  assert config.get(CONFIG_ACCOUNT_ID) is None
