"""Taking over from the folder this integration used to live in.

HACS works out where to put an integration from the domain in its manifest, so 21.0.0
installs into `custom_components/edfenergy_uk` and the old `custom_components/edf_energy`
is simply left behind. The config entries for the old domain stay in `.storage` whether or
not that folder is still there, which is what makes a hand-over possible at all: they can
be read, copied across and removed from here.

The point of all this is that nothing a user built should notice. Two things make that
achievable, and neither is luck:

* every unique_id is a literal `edf_energy_...` string rather than one built from DOMAIN, so
  an entity created under the new domain generates the same entity_id it had before - which
  is what automations, scripts, dashboards, template sensors and the energy dashboard
  actually reference
* every storage key is a literal `edf_energy.*`, so off-peak history, dispatch history and
  session history carry over without being touched

What genuinely is tied to the domain, and so has to be moved here:

* device identifiers are `(DOMAIN, ...)`, so the devices are recreated. Their area and any
  name the user gave them is captured and put back
* nothing, in the case of external statistics. They were going to be renamed, until the
  recorder turned out not to be able to: update_statistic_id filters on `source` being
  "recorder", so renaming one with a source of its own quietly matches no rows and reports
  success. They are written under the old prefix for good instead, which is why there is
  nothing here to do about them
* the entity registry keys on (platform, unique_id) and platform cannot be edited, so the
  old rows have to go before the new entities are created or every entity_id would come
  back with a `_2` suffix. Removing the old config entry is what removes them, and it is
  the one irreversible step here
"""
import logging

from homeassistant.config_entries import SOURCE_IMPORT
from homeassistant.helpers import device_registry as dr, entity_registry as er

from .const import DATA_MIGRATION, DOMAIN, PREDECESSOR_DOMAIN

_LOGGER = logging.getLogger(__name__)

# What a user can change about an entity that the integration would not set again itself.
# Anything the platform provides (original_name, device_class and so on) is recreated from
# the code and is deliberately not carried over.
_ENTITY_CUSTOMISATIONS = ("name", "icon", "area_id", "labels", "hidden_by", "disabled_by")


def device_identifier_suffix(identifiers, domain: str) -> str | None:
  """The part of a device's identifier that is not the domain, e.g. `gas_123_456`.

  Devices are matched across the move by this, because the domain half is exactly what
  changes and the rest is derived from the meter or device itself.
  """
  for identifier in identifiers or ():
    if isinstance(identifier, (tuple, list)) and len(identifier) == 2 and identifier[0] == domain:
      return identifier[1]
  return None


def capture_entities(registry, old_domain: str = PREDECESSOR_DOMAIN) -> dict:
  """What to put back on each entity after the hand-over, keyed by unique_id.

  The entity_id is captured as well as the customisations: it should be regenerated
  identically, and keeping it means that can be checked rather than assumed.
  """
  captured = {}
  for entry in registry.entities.values():
    if entry.platform != old_domain:
      continue
    captured[entry.unique_id] = {
      "entity_id": entry.entity_id,
      **{field: getattr(entry, field, None) for field in _ENTITY_CUSTOMISATIONS},
    }
  return captured


def capture_devices(registry, old_domain: str = PREDECESSOR_DOMAIN) -> dict:
  """Each old device's area and user-given name, keyed by its identifier suffix."""
  captured = {}
  for device in registry.devices.values():
    suffix = device_identifier_suffix(device.identifiers, old_domain)
    if suffix is None:
      continue
    captured[suffix] = {
      "area_id": device.area_id,
      "name_by_user": device.name_by_user,
      "labels": device.labels,
    }
  return captured


def apply_entity_customisations(registry, captured: dict) -> tuple[int, list[str]]:
  """Put the captured customisations back. Returns (how many, which ids had to be forced).

  An entity_id that came back different means something else claimed it in the meantime,
  so it is moved to the one it had before - an automation refers to the id, and a `_2`
  suffix is the whole failure this migration exists to avoid.
  """
  restored, forced = 0, []
  for entry in list(registry.entities.values()):
    if entry.platform != DOMAIN:
      continue
    was = captured.get(entry.unique_id)
    if was is None:
      continue

    updates = {
      field: was[field] for field in _ENTITY_CUSTOMISATIONS
      if was.get(field) is not None and was.get(field) != getattr(entry, field, None)
    }
    if was["entity_id"] != entry.entity_id:
      updates["new_entity_id"] = was["entity_id"]
      forced.append(was["entity_id"])

    if updates:
      try:
        registry.async_update_entity(entry.entity_id, **updates)
        restored += 1
      except Exception as err:
        # One entity that cannot be put back is not worth abandoning the rest for.
        _LOGGER.warning("Could not restore %s after the move: %s", entry.entity_id, err)
  return restored, forced


def apply_device_customisations(registry, captured: dict) -> int:
  """Put the captured area, name and labels back on the recreated devices."""
  restored = 0
  for device in list(registry.devices.values()):
    suffix = device_identifier_suffix(device.identifiers, DOMAIN)
    if suffix is None:
      continue
    was = captured.get(suffix)
    if was is None:
      continue

    updates = {}
    if was.get("area_id") and was["area_id"] != device.area_id:
      updates["area_id"] = was["area_id"]
    if was.get("name_by_user") and was["name_by_user"] != device.name_by_user:
      updates["name_by_user"] = was["name_by_user"]
    if was.get("labels") and was["labels"] != device.labels:
      updates["labels"] = was["labels"]

    if updates:
      try:
        registry.async_update_device(device.id, **updates)
        restored += 1
      except Exception as err:
        _LOGGER.warning("Could not restore device %s after the move: %s", suffix, err)
  return restored


async def async_take_over_old_entries(hass) -> int:
  """Move every config entry from the old domain to this one. Returns how many.

  Order matters and is the whole trick. The old entries are removed *before* the new ones
  are created, because removing a config entry is what removes its entity registry rows,
  and those rows own the entity_ids the new entities need to be given. Creating first and
  removing after would hand every entity a `_2` suffix, which is the breakage this is
  meant to prevent.

  External statistics need nothing doing to them. Their ids keep the prefix they were
  written with, because the recorder cannot rename an external statistic, so the Energy
  dashboard's history carries over by not being touched.
  """
  old_entries = list(hass.config_entries.async_entries(PREDECESSOR_DOMAIN))
  if not old_entries:
    return 0

  entity_registry = er.async_get(hass)
  device_registry = dr.async_get(hass)

  captured = {
    "entities": capture_entities(entity_registry),
    "devices": capture_devices(device_registry),
  }
  _LOGGER.info(
    "Taking over %d config entry(s) from %s: %d entity(s) and %d device(s) to carry across",
    len(old_entries), PREDECESSOR_DOMAIN,
    len(captured["entities"]), len(captured["devices"]),
  )
  hass.data.setdefault(DOMAIN, {})[DATA_MIGRATION] = captured

  # Everything needed from the old entries, read before they go.
  carried = [
    {
      "data": dict(entry.data),
      "options": dict(entry.options),
      "title": entry.title,
      "unique_id": entry.unique_id,
      "minor_version": getattr(entry, "minor_version", 1),
    }
    for entry in old_entries
  ]

  for entry in old_entries:
    await hass.config_entries.async_remove(entry.entry_id)

  for payload in carried:
    hass.async_create_task(
      hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_IMPORT}, data=payload
      )
    )
  return len(carried)


def async_apply_captured(hass) -> None:
  """Put the captured customisations back, once the new entities exist.

  Called after the platforms have been set up, so there is something to put them on. The
  capture is left in place rather than cleared: a second account's entry sets up separately
  and needs the same information.
  """
  captured = (hass.data.get(DOMAIN) or {}).get(DATA_MIGRATION)
  if not captured:
    return

  entities, forced = apply_entity_customisations(er.async_get(hass), captured["entities"])
  devices = apply_device_customisations(dr.async_get(hass), captured["devices"])
  if entities or devices:
    _LOGGER.info("Restored %d entity customisation(s) and %d device(s) after the move",
                 entities, devices)
  if forced:
    _LOGGER.warning(
      "These entity ids had to be moved back after the hand-over, so something else had "
      "taken them: %s", ", ".join(sorted(forced))
    )
