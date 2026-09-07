"""Flextras scheme support."""
import logging

from homeassistant.helpers import entity_registry as er

_LOGGER = logging.getLogger(__name__)


def async_remove_ineligible_entity(hass, platform: str, unique_id: str) -> None:
  """Drop a scheme entity the account is no longer eligible for.

  Gating entity *creation* is not enough on its own: an entity created before the
  account became ineligible (or before this gating existed) stays in the registry
  and renders as 'unavailable' forever. Removing it keeps the dashboard honest.
  """
  try:
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(platform, "edf_energy", unique_id)
    if entity_id is not None:
      registry.async_remove(entity_id)
      _LOGGER.info("Removed ineligible Flextras entity %s", entity_id)
  except Exception as e:
    _LOGGER.debug("Could not remove ineligible entity %s: %s", unique_id, e)
