"""Working out what an entry is, and putting back what it is missing."""

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
  DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

# What the cost tracker discovery flow builds its unique id out of, in both this domain and
# the one it was forked from. The account id and the entity being tracked are both in there,
# which is the only place they survive on an entry that has lost them from its data.
COST_TRACKER_UNIQUE_ID_MARKER = "_ct_"

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

def recover_cost_tracker_from_unique_id(unique_id) -> dict | None:
  """The account and tracked entity read back out of a discovered cost tracker's unique id.

  Auto discovered cost trackers are given "<domain>_ct_<account id>_<entity id>", which is
  the account id and the entity being tracked spelled out in a field that lives beside the
  data rather than in it. An entry that has lost both from its data can be put back together
  from this, which is the difference between the user getting their cost trackers back and
  being told to delete thirty eight of them and start again.

  Returns None unless it is confident: account ids carry no underscore and entity ids always
  carry a dot, so anything that does not split cleanly is left alone.
  """
  if not unique_id or not isinstance(unique_id, str):
    return None

  marker_at = unique_id.find(COST_TRACKER_UNIQUE_ID_MARKER)
  if marker_at < 0:
    return None

  remainder = unique_id[marker_at + len(COST_TRACKER_UNIQUE_ID_MARKER):]
  account_id, separator, target_entity_id = remainder.partition("_")
  if not separator or not account_id or "." not in target_entity_id:
    return None

  return {
    CONFIG_ACCOUNT_ID: account_id,
    CONFIG_COST_TRACKER_TARGET_ENTITY_ID: target_entity_id,
  }

def find_sole_account_id(hass, exclude_entry_id=None) -> str | None:
  """The account id, when exactly one account is configured.

  A child entry that has lost its account id can only be reconnected if there is no question
  which account it belonged to. With one account there is none. With two there is, and
  guessing would attach someone's cost tracker to the wrong account's rates, so this gives
  up instead.
  """
  account_ids = set()
  for entry in hass.config_entries.async_entries(DOMAIN, include_ignore=False):
    if exclude_entry_id is not None and entry.entry_id == exclude_entry_id:
      continue

    config = dict(entry.data)
    if get_config_kind(config) == CONFIG_KIND_ACCOUNT and CONFIG_ACCOUNT_ID in config:
      account_ids.add(config[CONFIG_ACCOUNT_ID])

  if len(account_ids) == 1:
    return next(iter(account_ids))

  return None

def async_repair_config_entry(hass, entry) -> dict:
  """An entry's data with whatever it has lost put back, recorded if anything changed.

  Entries turn up having lost the kind that says what they are and the account id that says
  what they belong to. Reading either of those straight out took setup down with a KeyError,
  and guarding the read only turns a crash into an entry that never works again. So rebuild
  what can be rebuilt - the unique id holds both for a discovered cost tracker, and a single
  configured account settles the account id for anything else - and write it back, so the
  entry is mended rather than tiptoed around for the rest of its life.

  Returns the repaired data. It can still be missing things, and the caller has to say so
  plainly rather than assume.
  """
  config = dict(entry.data)
  repaired = dict(config)

  from_unique_id = recover_cost_tracker_from_unique_id(getattr(entry, "unique_id", None))
  if from_unique_id is not None:
    for key, value in from_unique_id.items():
      repaired.setdefault(key, value)
    repaired.setdefault(CONFIG_KIND, CONFIG_KIND_COST_TRACKER)

  kind = repaired.get(CONFIG_KIND) or infer_config_kind(repaired)

  # Only a child entry can borrow the account id. An account entry that has lost its own is
  # beyond this, and taking another account's id would quietly merge the two.
  if kind is not None and kind != CONFIG_KIND_ACCOUNT and CONFIG_ACCOUNT_ID not in repaired:
    sole_account_id = find_sole_account_id(hass, exclude_entry_id=entry.entry_id)
    if sole_account_id is not None:
      repaired[CONFIG_ACCOUNT_ID] = sole_account_id

  if kind is not None:
    repaired.setdefault(CONFIG_KIND, kind)

  if repaired == config:
    return config

  hass.config_entries.async_update_entry(entry, data=repaired)
  _LOGGER.warning(
    "Config entry '%s' was missing %s; recovered it and repaired the entry",
    entry.title, ", ".join(sorted(set(repaired) - set(config))),
  )
  return repaired

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

  repaired = async_repair_config_entry(hass, entry)
  return repaired.get(CONFIG_KIND)
