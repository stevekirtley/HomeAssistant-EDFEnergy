"""Working out what an entry is when it has no kind recorded."""

import logging

from ..const import (
  CONFIG_COST_TRACKER_TARGET_ENTITY_ID,
  CONFIG_KIND,
  CONFIG_KIND_ACCOUNT,
  CONFIG_KIND_COST_TRACKER,
  CONFIG_KIND_TARIFF_COMPARISON,
  CONFIG_TARIFF_COMPARISON_PRODUCT_CODE,
)

_LOGGER = logging.getLogger(__name__)

def infer_config_kind(config: dict) -> str:
  """Work out what an entry is when it has no kind recorded.

  Every kind carries the account id, so that cannot tell them apart. Each child kind has
  a field of its own that an account entry never has, so look for those first and fall
  back to an account, which is what the great majority of entries are.
  """
  if CONFIG_COST_TRACKER_TARGET_ENTITY_ID in config:
    return CONFIG_KIND_COST_TRACKER
  if CONFIG_TARIFF_COMPARISON_PRODUCT_CODE in config:
    return CONFIG_KIND_TARIFF_COMPARISON
  # Target rates are not offered by this fork, so there is nothing to detect them by and
  # nothing to detect.
  return CONFIG_KIND_ACCOUNT

def get_config_kind(config: dict) -> str:
  """The kind of an entry, inferred if it was never recorded.

  Entries carried over from the old domain keep their data verbatim and are created at
  the current config version, so one that never had a kind recorded does not get one from
  the migration. It repairs itself when it is set up, but a disabled entry is never set
  up, so it stays without one through every restart. Anything that walks the other entries
  has to cope with that rather than reading the key straight out.
  """
  return config.get(CONFIG_KIND) or infer_config_kind(config)

def async_ensure_config_kind(hass, entry) -> str:
  """The kind of an entry, written back onto it when it was missing.

  An entry that reaches the current config version without a kind repairs itself when it is
  set up. A disabled entry is never set up, so it never gets that far: it keeps turning up
  in async_entries with nothing to say what it is, and every caller that walks past it has
  to cope. Recording the inferred kind the first time anything looks at it ends that, rather
  than every reader working around it forever.
  """
  config = dict(entry.data)
  recorded = config.get(CONFIG_KIND)
  if recorded:
    return recorded

  kind = infer_config_kind(config)
  config[CONFIG_KIND] = kind
  hass.config_entries.async_update_entry(entry, data=config)
  _LOGGER.warning(
    "Config entry '%s' had no kind recorded; treating it as '%s' and repairing it",
    entry.title, kind,
  )
  return kind
