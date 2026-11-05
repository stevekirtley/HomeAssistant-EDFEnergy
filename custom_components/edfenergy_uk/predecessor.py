"""Telling the edf_energy this integration replaced apart from somebody else's.

`edf_energy` is not ours alone. Bobby5291/HomeAssistant-EDF-UK is a separate EDF integration
in the HACS catalog, and it installs into `custom_components/edf_energy` under that same
domain. So a folder or a config entry on that domain is only our predecessor when it can be
shown to be: anything done to the other one - deleting its folder, taking its entries over,
clearing its repairs, registering actions under its name - breaks an integration that has
nothing to do with us.

What proves it:

* the folder: its manifest names this repository's owner or this repository. Every release
  that ever shipped `custom_components/edf_energy` from here carries both, and the other
  integration carries neither
* an entry: config version 9 and one of our kinds. Every entry this integration ever created
  on the old domain is version 9, because the flow it came from was already at 9 when it was
  forked, and the other integration's flow is at 1. An ignored suggestion has no data, so no
  kind, but is version 9 all the same. An entry from before the kind was recorded counts too,
  but only when the folder on disk is ours

Anything else is left exactly as it is.
"""
import json
import os

from homeassistant.config_entries import SOURCE_IGNORE

from .const import (
  CONFIG_ACCOUNT_ID,
  CONFIG_KIND,
  CONFIG_KIND_ACCOUNT,
  CONFIG_KIND_COST_TRACKER,
  CONFIG_KIND_ROLLING_TARGET_RATE,
  CONFIG_KIND_TARGET_RATE,
  CONFIG_KIND_TARIFF_COMPARISON,
  DATA_PREDECESSOR_FOLDER,
  DOMAIN,
  PREDECESSOR_DOMAIN,
)

OUR_CODEOWNER = "@stevekirtley"
OUR_REPOSITORY = "github.com/stevekirtley/homeassistant-edfenergy"
PREDECESSOR_CONFIG_VERSION = 9

FOLDER_OURS = "ours"
FOLDER_NOT_OURS = "not_ours"

_OUR_KINDS = {
  CONFIG_KIND_ACCOUNT,
  CONFIG_KIND_TARGET_RATE,
  CONFIG_KIND_ROLLING_TARGET_RATE,
  CONFIG_KIND_COST_TRACKER,
  CONFIG_KIND_TARIFF_COMPARISON,
}


def manifest_is_ours(manifest) -> bool:
  """Whether a manifest is one this repository shipped under the old domain."""
  if not isinstance(manifest, dict) or manifest.get("domain") != PREDECESSOR_DOMAIN:
    return False

  codeowners = manifest.get("codeowners")
  if isinstance(codeowners, list) and OUR_CODEOWNER in codeowners:
    return True

  return any(
    isinstance(manifest.get(key), str) and OUR_REPOSITORY in manifest[key].lower()
    for key in ("documentation", "issue_tracker")
  )


def predecessor_folder_path(config_dir: str) -> str:
  return os.path.join(config_dir, "custom_components", PREDECESSOR_DOMAIN)


def read_predecessor_folder(config_dir: str) -> tuple[str | None, str | None]:
  """Who `custom_components/edf_energy` belongs to, and the version it says it is.

  (None, None) when there is no such folder. A folder whose manifest cannot be read is not
  ours: it cannot be shown to be, and the safe thing to do with a folder of unknown origin is
  nothing. Reads a file, so it belongs in the executor.
  """
  folder = predecessor_folder_path(config_dir)
  if not os.path.isdir(folder):
    return None, None

  try:
    with open(os.path.join(folder, "manifest.json"), encoding="utf-8") as handle:
      manifest = json.load(handle)
  except Exception:
    return FOLDER_NOT_OURS, None

  if not manifest_is_ours(manifest):
    return FOLDER_NOT_OURS, None
  return FOLDER_OURS, str(manifest.get("version") or "") or "unknown"


def is_our_old_entry(entry, folder: str | None) -> bool:
  """Whether a config entry on the old domain was created by this integration."""
  if getattr(entry, "version", None) != PREDECESSOR_CONFIG_VERSION:
    return False

  if getattr(entry, "source", None) == SOURCE_IGNORE:
    return True

  kind = (getattr(entry, "data", None) or {}).get(CONFIG_KIND)
  if kind is not None:
    return kind in _OUR_KINDS

  return folder == FOLDER_OURS


def our_old_entries(hass, folder: str | None) -> list:
  return [
    entry for entry in hass.config_entries.async_entries(PREDECESSOR_DOMAIN)
    if is_our_old_entry(entry, folder)
  ]


def other_integration_entries(hass, folder: str | None) -> list:
  """Entries on the old domain that belong to the other integration and are in use."""
  return [
    entry for entry in hass.config_entries.async_entries(PREDECESSOR_DOMAIN)
    if not is_our_old_entry(entry, folder)
    and getattr(entry, "source", None) != SOURCE_IGNORE
    and not getattr(entry, "disabled_by", None)
  ]


def known_folder(hass) -> str | None:
  """The folder's owner as read when the integration set up, or not ours if it never was."""
  return (hass.data.get(DOMAIN) or {}).get(DATA_PREDECESSOR_FOLDER, FOLDER_NOT_OURS)


def old_domain_is_ours_or_gone(hass, folder: str | None) -> bool:
  """Whether nothing but this integration has any claim on the old domain.

  Only then is it safe to register actions under it or clear its repairs.
  """
  return folder != FOLDER_NOT_OURS and not other_integration_entries(hass, folder)


def accounts_shared_with_other_integration(hass, folder: str | None = None) -> set[str]:
  """Our account ids that the other integration also has set up.

  On a shared account both write the same `edf_energy:` statistics and the same account
  store, and each overwrites the other's Energy dashboard history.
  """
  if folder is None:
    folder = known_folder(hass)

  theirs = {
    str((entry.data or {}).get(CONFIG_ACCOUNT_ID) or "").lower()
    for entry in other_integration_entries(hass, folder)
  }
  theirs.discard("")
  if not theirs:
    return set()

  ours = {
    str((entry.data or {}).get(CONFIG_ACCOUNT_ID) or "")
    for entry in hass.config_entries.async_entries(DOMAIN)
    if (entry.data or {}).get(CONFIG_KIND) == CONFIG_KIND_ACCOUNT
  }
  return {account for account in ours if account and account.lower() in theirs}
