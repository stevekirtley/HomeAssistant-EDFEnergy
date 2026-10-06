"""A config entry that lost its 'kind' used to break setup permanently.

Reported on Reddit against 19.2.4: `KeyError: 'kind'` from async_setup_entry, with the
integration showing "Failed to set up". The entry had an account id but no kind, and
nothing could put it right - the migration that fills the kind in only runs while the
entry is below the current config version, so an entry already at the current version
stayed broken through every restart. 19.2.4 did not cause it; updating merely forced the
reload that showed it.
"""
import pytest

from custom_components.edf_energy import _infer_config_kind
from custom_components.edf_energy.const import (
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
