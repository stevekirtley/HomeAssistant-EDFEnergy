"""What the panel puts in a banner: a new release, and anything urgent from the relay.

Two separate things, because they answer different questions and arrive by different routes.

The release banner comes from HACS. HACS already polls GitHub for this integration and
publishes an update entity carrying the installed and latest versions, the release url and
whichever version the user chose to skip - so this reads that entity rather than calling
GitHub again. An install without HACS has no such entity and simply gets no release banner;
somebody managing updates by hand has opted out of being told.

The urgent notice comes from the relay, because HACS only refreshes its catalogue every few
hours and that is too slow when a release has to reach people quickly. It rides on the feed
the integration already polls every quarter of an hour, so it costs no extra request and
arrives within fifteen minutes rather than overnight.
"""

import logging

from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import DOMAIN, INTEGRATION_VERSION

_LOGGER = logging.getLogger(__name__)

HACS_PLATFORM = "hacs"
# HACS points the entity picture at the brands icon for the integration it manages, which is
# keyed by the integration's own domain - the one signal in the entity that names us.
BRANDS_FRAGMENT = f"/{DOMAIN}/"


def _is_newer(latest, installed) -> bool:
  """Whether latest is a higher version than installed, comparing numerically.

  A string compare gets this wrong in the obvious place: "19.9.0" > "19.10.0" is true as
  text and false as versions. Anything unparseable answers False, because telling somebody
  to update on the strength of a version we could not read is worse than staying quiet.
  """
  if not isinstance(latest, str) or not isinstance(installed, str):
    return False

  def parts(value):
    cleaned = value.strip().lstrip("vV")
    try:
      return [int(part) for part in cleaned.split(".")]
    except (TypeError, ValueError):
      return None

  left, right = parts(latest), parts(installed)
  if left is None or right is None:
    return False
  length = max(len(left), len(right))
  left += [0] * (length - len(left))
  right += [0] * (length - len(right))
  return left > right


def find_hacs_update_entity(hass) -> str | None:
  """The entity id of the HACS update entity for this integration, if there is one.

  Matched through the registries rather than by guessing `update.edf_energy_update`, which
  is only the default and does not survive a rename. A HACS update entity is identified by
  its brands picture naming our domain, or failing that by its device carrying the name
  HACS gives the repository and reporting the version we are actually running.
  """
  try:
    entities = er.async_get(hass)
    devices = dr.async_get(hass)
  except Exception:  # pragma: no cover - registries are always there in practice
    return None

  candidates = [
    entry for entry in entities.entities.values()
    if entry.platform == HACS_PLATFORM and entry.domain == "update" and not entry.disabled_by
  ]

  for entry in candidates:
    state = hass.states.get(entry.entity_id)
    if state is None:
      continue
    picture = state.attributes.get("entity_picture")
    if isinstance(picture, str) and BRANDS_FRAGMENT in picture:
      return entry.entity_id

  # No brands picture - fall back to the device HACS created for the repository. Its stored
  # name is used rather than any rename the user has made, and the installed version has to
  # agree with ours so another repository cannot be mistaken for this one.
  for entry in candidates:
    if entry.device_id is None:
      continue
    device = devices.async_get(entry.device_id)
    if device is None or device.name != "EDF Energy":
      continue
    state = hass.states.get(entry.entity_id)
    if state is not None and state.attributes.get("installed_version") == INTEGRATION_VERSION:
      return entry.entity_id

  return None


def build_release_notice(hass) -> dict | None:
  """The release banner, or None when there is nothing to say.

  Nothing is said when HACS is not installed, when the versions match, or when the user has
  already told HACS to skip this version - skipping is an answer, and asking again in a
  different place would just be nagging.
  """
  entity_id = find_hacs_update_entity(hass)
  if entity_id is None:
    return None

  state = hass.states.get(entity_id)
  if state is None:
    return None

  attributes = state.attributes
  installed = attributes.get("installed_version") or INTEGRATION_VERSION
  latest = attributes.get("latest_version")
  if not _is_newer(latest, installed):
    return None
  if attributes.get("skipped_version") == latest:
    return None

  return {
    "installed": installed,
    "latest": latest,
    "url": attributes.get("release_url"),
    "summary": attributes.get("release_summary"),
  }
