"""The deprecated action aliases carry their own description.

Home Assistant reads an action's description from the services.yaml of the integration that
owns its domain. The aliases are registered under `edf_energy`, and the whole point of this
release is that the user deletes that folder - after which the lookup finds no integration
and logs `Failed to load services.yaml for integration: edf_energy` on every start, which
looks like a broken install and is the first thing anybody would open an issue about.

Registering a description puts it in the cache that lookup checks first, so the file is
never wanted. It also means the alias says in the UI that it is deprecated.
"""
from homeassistant.core import SupportsResponse

from custom_components.edfenergy_uk.const import DOMAIN, PREDECESSOR_DOMAIN
from custom_components.edfenergy_uk.utils.entity_services import describe_alias


class StubServices:
  def supports_response(self, domain, service):
    return SupportsResponse.NONE


class StubHass:
  def __init__(self):
    self.data = {}
    self.services = StubServices()


def _described(hass):
  """What async_set_service_schema wrote, keyed by (domain, service)."""
  for value in hass.data.values():
    if isinstance(value, dict) and value:
      return value
  return {}


def test_an_alias_is_described_under_the_old_domain():
  hass = StubHass()

  describe_alias(hass, "refresh_intelligent_dispatches")

  cache = _described(hass)
  assert (PREDECESSOR_DOMAIN, "refresh_intelligent_dispatches") in cache, cache
  assert (DOMAIN, "refresh_intelligent_dispatches") not in cache, \
    "the current domain reads its description from our own services.yaml"


def test_the_description_sends_people_at_the_current_name():
  hass = StubHass()

  describe_alias(hass, "update_cost_tracker")

  blob = str(_described(hass))
  assert f"{DOMAIN}.update_cost_tracker" in blob
  assert "deprecated" in blob.lower()
