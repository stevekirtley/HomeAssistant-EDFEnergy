"""Working out what an entry is when it has no kind recorded."""

import logging

from ..const import (
  CONFIG_ACCOUNT_ID,
  CONFIG_COST_TRACKER_MPAN,
  CONFIG_COST_TRACKER_NAME,
  CONFIG_COST_TRACKER_TARGET_ENTITY_ID,
  CONFIG_KIND,
  CONFIG_KIND_ACCOUNT,
  CONFIG_KIND_COST_TRACKER,
  CONFIG_KIND_TARIFF_COMPARISON,
  CONFIG_MAIN_API_KEY,
  CONFIG_MAIN_OLD_API_KEY,
  CONFIG_TARIFF_COMPARISON_MPAN_MPRN,
  CONFIG_TARIFF_COMPARISON_NAME,
  CONFIG_TARIFF_COMPARISON_PRODUCT_CODE,
  CONFIG_TARIFF_COMPARISON_TARIFF_CODE,
)

_LOGGER = logging.getLogger(__name__)

# What each kind cannot be set up without. Every one of these is read by key somewhere past
# setup - in the sensor, or in the tracker itself - so an entry that has lost one fails
# somewhere that says nothing about what is actually wrong. Checked once, up front, instead.
REQUIRED_FIELDS_BY_KIND = {
  CONFIG_KIND_COST_TRACKER: (
    CONFIG_COST_TRACKER_NAME,
    CONFIG_COST_TRACKER_MPAN,
    CONFIG_COST_TRACKER_TARGET_ENTITY_ID,
  ),
  CONFIG_KIND_TARIFF_COMPARISON: (
    CONFIG_TARIFF_COMPARISON_NAME,
    CONFIG_TARIFF_COMPARISON_MPAN_MPRN,
    CONFIG_TARIFF_COMPARISON_PRODUCT_CODE,
    CONFIG_TARIFF_COMPARISON_TARIFF_CODE,
  ),
}

def missing_required_fields(kind, config: dict) -> list:
  """What an entry still needs and has not got, after everything recoverable is back.

  Called once setup has repaired what it can. An entry that gets this far missing something
  cannot be made to work by carrying on, and the user is the only one who can put it right,
  so the answer is to name the fields rather than fail somewhere further in on whichever one
  happened to be read first.
  """
  missing = []

  if CONFIG_ACCOUNT_ID not in config:
    missing.append(CONFIG_ACCOUNT_ID)

  missing.extend(key for key in REQUIRED_FIELDS_BY_KIND.get(kind, ()) if key not in config)

  return missing

def infer_config_kind(config: dict) -> str | None:
  """Work out what an entry is when it has no kind recorded.

  Positive evidence only. Each child kind has a field of its own that an account entry never
  has, and an account carries credentials that a child never does, so look for those. An
  entry that matches none of them gets None rather than a guess: labelling something an
  account because nothing identified it is how a cost tracker ends up recorded as the
  account it belongs to, and that mistake gets written to disk and never questioned again.
  """
  if CONFIG_COST_TRACKER_TARGET_ENTITY_ID in config:
    return CONFIG_KIND_COST_TRACKER
  if CONFIG_TARIFF_COMPARISON_PRODUCT_CODE in config:
    return CONFIG_KIND_TARIFF_COMPARISON
  # Only an account is ever given credentials, so they settle it on their own.
  if CONFIG_MAIN_API_KEY in config or CONFIG_MAIN_OLD_API_KEY in config:
    return CONFIG_KIND_ACCOUNT
  # Failing that, an entry that carries an account id and nothing that marks it as a child
  # is an account, which is what the great majority of entries are.
  if CONFIG_ACCOUNT_ID in config:
    return CONFIG_KIND_ACCOUNT
  # Target rates are not offered by this fork, so there is nothing to detect them by and
  # nothing to detect.
  return None

def get_config_kind(config: dict) -> str | None:
  """The kind of an entry, inferred if it was never recorded.

  Entries carried over from the old domain keep their data verbatim and are created at
  the current config version, so one that never had a kind recorded does not get one from
  the migration. It repairs itself when it is set up, but a disabled entry is never set
  up, so it stays without one through every restart. Anything that walks the other entries
  has to cope with that rather than reading the key straight out.

  May be None, for an entry with nothing left on it to say what it is. Nothing matches None,
  so a caller comparing against a particular kind needs no extra guard.
  """
  return config.get(CONFIG_KIND) or infer_config_kind(config)

def async_record_inferred_kind(hass, entry) -> dict:
  """An entry's data, with its kind written back onto it when it was missing and can be told.

  An entry that reached the current config version without a kind does not get one from the
  migration, which only runs below that version, so it stayed without one through every
  restart. Recording it once, from positive evidence, mends it for good. An entry that
  nothing identifies is left exactly as it is - recording a guess would make the guess
  permanent and hide whatever actually went wrong.
  """
  config = dict(entry.data)
  if config.get(CONFIG_KIND):
    return config

  kind = infer_config_kind(config)
  if kind is None:
    return config

  config[CONFIG_KIND] = kind
  hass.config_entries.async_update_entry(entry, data=config)
  _LOGGER.warning(
    "Config entry '%s' had no kind recorded; treating it as '%s' and repairing it",
    entry.title, kind,
  )
  return config

def async_ensure_config_kind(hass, entry) -> str | None:
  """The kind of an entry, written back onto it when it was missing.

  An entry that reaches the current config version without a kind repairs itself when it is
  set up. A disabled entry is never set up, so it never gets that far: it keeps turning up
  in async_entries with nothing to say what it is, and every caller that walks past it has
  to cope. Recording the inferred kind the first time anything looks at it ends that, rather
  than every reader working around it forever.

  An entry that nothing identifies is left exactly as it is. Writing a guess onto it would
  make the guess permanent and hide the real problem.
  """
  config = dict(entry.data)
  recorded = config.get(CONFIG_KIND)
  if recorded:
    return recorded

  return async_record_inferred_kind(hass, entry).get(CONFIG_KIND)
